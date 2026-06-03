from flask import Flask, render_template, send_file, request, abort, jsonify
import os
import zipfile
import shutil
import json
import logging
from io import BytesIO
from datetime import datetime
import mimetypes
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import psutil

app = Flask(__name__)

ROOT_PATH = '/home/user'
MAX_UPLOAD_SIZE = int(os.environ.get('MAX_UPLOAD_SIZE', 10 * 1024 * 1024 * 1024))   # 10 GB
MAX_ZIP_SIZE    = int(os.environ.get('MAX_ZIP_SIZE',    4  * 1024 * 1024 * 1024))   # 4 GB
MAX_SEARCH_DEPTH   = int(os.environ.get('MAX_SEARCH_DEPTH', 10))
MAX_SEARCH_RESULTS = 100

app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


# ── Helpers ──────────────────────────────────────────────────────────────────

@app.errorhandler(RequestEntityTooLarge)
def handle_too_large(_e):
    limit_gb = MAX_UPLOAD_SIZE // (1024 ** 3)
    return jsonify({'error': f'Fichier trop volumineux (max {limit_gb} GB)'}), 413


def safe_path(subpath):
    """Returns the absolute full path if it stays within ROOT_PATH, else None."""
    full = os.path.join(ROOT_PATH, subpath) if subpath else ROOT_PATH
    if os.path.abspath(full).startswith(os.path.abspath(ROOT_PATH)):
        return full
    return None


def get_file_info(path):
    stats = os.stat(path)
    return {
        'name': os.path.basename(path),
        'size': stats.st_size,
        'modified': datetime.fromtimestamp(stats.st_mtime),
        'is_dir': os.path.isdir(path),
    }


def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def get_directory_listing(path, show_hidden=False):
    items = []
    try:
        for name in os.listdir(path):
            if not show_hidden and name.startswith('.'):
                continue
            try:
                items.append(get_file_info(os.path.join(path, name)))
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        return []
    items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
    return items


def items_to_json(items):
    return [
        {
            'name': item['name'],
            'size': item['size'],
            'size_formatted': format_size(item['size']) if not item['is_dir'] else '-',
            'modified': item['modified'].strftime('%Y-%m-%d %H:%M'),
            'is_dir': item['is_dir'],
        }
        for item in items
    ]


def compute_total_size(paths):
    """Recursively compute total size of files, skipping symlinks."""
    total = 0
    for path in paths:
        if os.path.islink(path):
            continue
        if os.path.isfile(path):
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        elif os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
                for f in files:
                    fp = os.path.join(root, f)
                    if not os.path.islink(fp):
                        try:
                            total += os.path.getsize(fp)
                        except OSError:
                            pass
    return total


def write_dir_to_zip(zf, dir_path, arcname_prefix):
    for root, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for f in files:
            fp = os.path.join(root, f)
            if not os.path.islink(fp):
                arcname = os.path.join(arcname_prefix, os.path.relpath(fp, dir_path))
                try:
                    zf.write(fp, arcname)
                except (OSError, PermissionError):
                    pass


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
@app.route('/<path:subpath>')
def index(subpath=''):
    current_path = safe_path(subpath)
    if not current_path:
        abort(403)
    if not os.path.exists(current_path):
        abort(404)
    if os.path.isfile(current_path):
        return send_file(current_path, as_attachment=True)

    show_hidden = request.args.get('show_hidden', 'false').lower() == 'true'
    items = get_directory_listing(current_path, show_hidden=show_hidden)

    breadcrumb = []
    if subpath:
        parts = subpath.split('/')
        for i, part in enumerate(parts):
            breadcrumb.append({'name': part, 'path': '/'.join(parts[:i + 1])})

    return render_template(
        'index.html',
        items_json=json.dumps(items_to_json(items)),
        current_path=subpath,
        breadcrumb=breadcrumb,
        show_hidden=show_hidden,
    )


@app.route('/list')
@app.route('/list/<path:subpath>')
def list_files(subpath=''):
    current_path = safe_path(subpath)
    if not current_path:
        abort(403)
    if not os.path.exists(current_path) or not os.path.isdir(current_path):
        abort(404)
    show_hidden = request.args.get('show_hidden', 'false').lower() == 'true'
    items = get_directory_listing(current_path, show_hidden=show_hidden)
    return jsonify({'items': items_to_json(items)})


@app.route('/preview/<path:filepath>')
def preview_file(filepath):
    full_path = safe_path(filepath)
    if not full_path:
        abort(403)
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        abort(404)
    return send_file(full_path, as_attachment=False)


@app.route('/download/<path:filepath>')
def download_file(filepath):
    full_path = safe_path(filepath)
    if not full_path:
        abort(403)
    if not os.path.exists(full_path):
        abort(404)
    if not os.path.isfile(full_path):
        abort(400)
    app.logger.info('Download: %s', filepath)
    return send_file(full_path, as_attachment=True)


@app.route('/download-multiple', methods=['POST'])
def download_multiple():
    names = request.form.getlist('files[]')
    base = request.form.get('current_path', '')
    if not names:
        abort(400)

    entries = []
    for name in names:
        rel = os.path.join(base, name) if base else name
        fp = safe_path(rel)
        if fp and os.path.exists(fp) and not os.path.islink(fp):
            entries.append((name, fp))

    if not entries:
        abort(400)

    total = compute_total_size([fp for _, fp in entries])
    if total > MAX_ZIP_SIZE:
        limit_gb = MAX_ZIP_SIZE // (1024 ** 3)
        return jsonify({'error': f'Sélection trop volumineuse (max {limit_gb} GB)'}), 413

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, fp in entries:
            if os.path.isfile(fp):
                zf.write(fp, name)
            elif os.path.isdir(fp):
                write_dir_to_zip(zf, fp, name)
    buf.seek(0)

    zip_name = f'{names[0]}.zip' if len(names) == 1 else 'files.zip'
    app.logger.info('Download ZIP: %s', names)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=zip_name)


@app.route('/download-all')
@app.route('/download-all/<path:subpath>')
def download_all(subpath=''):
    current_path = safe_path(subpath)
    if not current_path:
        abort(403)
    if not os.path.exists(current_path) or not os.path.isdir(current_path):
        abort(404)

    total = compute_total_size([current_path])
    if total > MAX_ZIP_SIZE:
        limit_gb = MAX_ZIP_SIZE // (1024 ** 3)
        return jsonify({'error': f'Dossier trop volumineux (max {limit_gb} GB)'}), 413

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        write_dir_to_zip(zf, current_path, '')
    buf.seek(0)

    folder_name = os.path.basename(current_path) if subpath else 'root'
    app.logger.info('Download all ZIP: %s', subpath)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f'{folder_name}.zip')


@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files[]' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400

    files = request.files.getlist('files[]')
    base = request.form.get('current_path', '')
    upload_path = safe_path(base)

    if not upload_path:
        return jsonify({'error': 'Accès refusé'}), 403
    if not os.path.exists(upload_path) or not os.path.isdir(upload_path):
        return jsonify({'error': 'Dossier de destination invalide'}), 400

    uploaded, errors = [], []
    for file in files:
        if not file.filename:
            continue
        filename = secure_filename(file.filename)
        if not filename:
            continue
        try:
            file.save(os.path.join(upload_path, filename))
            uploaded.append(filename)
            app.logger.info('Upload: %s -> %s', filename, base)
        except Exception:
            app.logger.exception('Upload failed: %s', file.filename)
            errors.append(file.filename)

    result = {'uploaded': uploaded, 'count': len(uploaded)}
    if errors:
        result['errors'] = [f'{f}: erreur lors de l\'upload' for f in errors]
    return jsonify(result)


@app.route('/delete', methods=['POST'])
def delete_file():
    filepath = request.form.get('path', '')
    if not filepath:
        return jsonify({'error': 'Chemin requis'}), 400

    full_path = safe_path(filepath)
    if not full_path:
        return jsonify({'error': 'Accès refusé'}), 403
    if not os.path.exists(full_path):
        return jsonify({'error': 'Fichier introuvable'}), 404

    try:
        if os.path.isfile(full_path) or os.path.islink(full_path):
            os.remove(full_path)
        elif os.path.isdir(full_path):
            shutil.rmtree(full_path)
        app.logger.info('Deleted: %s', filepath)
        return jsonify({'success': True})
    except Exception:
        app.logger.exception('Delete failed: %s', filepath)
        return jsonify({'error': 'Suppression échouée'}), 500


@app.route('/search')
def search_files():
    query = request.args.get('q', '').lower().strip()
    base = request.args.get('path', '')
    show_hidden = request.args.get('show_hidden', 'false').lower() == 'true'

    if not query:
        return jsonify({'results': []})

    search_path = safe_path(base)
    if not search_path:
        abort(403)
    if not os.path.exists(search_path):
        return jsonify({'results': []})

    results = []
    base_depth = search_path.rstrip(os.sep).count(os.sep)

    try:
        for root, dirs, files in os.walk(search_path):
            depth = root.rstrip(os.sep).count(os.sep) - base_depth
            if depth >= MAX_SEARCH_DEPTH:
                dirs.clear()
                continue

            if not show_hidden:
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                files   = [f for f in files if not f.startswith('.')]

            for dirname in dirs:
                if query in dirname.lower():
                    rel = os.path.relpath(os.path.join(root, dirname), ROOT_PATH)
                    results.append({'name': dirname, 'path': rel, 'is_dir': True})

            for filename in files:
                if query in filename.lower():
                    fp = os.path.join(root, filename)
                    rel = os.path.relpath(fp, ROOT_PATH)
                    try:
                        stats = os.stat(fp)
                        results.append({
                            'name': filename,
                            'path': rel,
                            'is_dir': False,
                            'size': stats.st_size,
                            'modified': datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M'),
                        })
                    except (OSError, PermissionError):
                        continue

            if len(results) >= MAX_SEARCH_RESULTS:
                break
    except (OSError, PermissionError):
        pass

    return jsonify({'results': results[:MAX_SEARCH_RESULTS]})


@app.route('/metrics')
def system_metrics():
    try:
        disk   = psutil.disk_usage(ROOT_PATH)
        memory = psutil.virtual_memory()

        temps_data = {'available': False, 'sensors': []}
        try:
            raw = psutil.sensors_temperatures()
            if raw:
                all_readings = []
                for chip, readings in raw.items():
                    for r in readings:
                        all_readings.append({
                            'chip':     chip,
                            'label':    r.label or chip,
                            'current':  r.current,
                            'high':     r.high,
                            'critical': r.critical,
                        })
                if all_readings:
                    temps_data = {
                        'available': True,
                        'sensors':   all_readings,
                        'max':       max(all_readings, key=lambda x: x['current']),
                    }
        except (AttributeError, Exception):
            pass

        return jsonify({
            'disk': {
                'used':    disk.used  / (1024 ** 3),
                'total':   disk.total / (1024 ** 3),
                'free':    disk.free  / (1024 ** 3),
                'percent': disk.percent,
            },
            'ram': {
                'used':    memory.used  / (1024 ** 3),
                'total':   memory.total / (1024 ** 3),
                'percent': memory.percent,
            },
            'cpu':  {'percent': psutil.cpu_percent(interval=0.1)},
            'temps': temps_data,
        })
    except Exception:
        app.logger.exception('Metrics error')
        return jsonify({'error': 'Erreur lors de la collecte des métriques'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
