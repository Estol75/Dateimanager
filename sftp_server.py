#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import paramiko
import io
import os
import stat
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app, supports_credentials=True, origins=["*"])

SSH_HOST = "ux5.edvschule-plattling.de"
SSH_PORT = 22
sessions = {}

def get_sftp(token):
    if token not in sessions:
        return None, None
    return sessions[token].get("sftp"), sessions[token].get("transport")

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Benutzername und Passwort erforderlich"}), 400
    try:
        transport = paramiko.Transport((SSH_HOST, SSH_PORT))
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        token = secrets.token_hex(32)
        sessions[token] = {"sftp": sftp, "transport": transport, "username": username}
        return jsonify({"token": token, "username": username})
    except paramiko.AuthenticationException:
        return jsonify({"error": "Falsches Passwort oder Benutzername"}), 401
    except Exception as e:
        return jsonify({"error": f"Verbindungsfehler: {str(e)}"}), 500

@app.route("/api/logout", methods=["POST"])
def logout():
    token = request.headers.get("X-Auth-Token")
    if token and token in sessions:
        try:
            sessions[token]["sftp"].close()
            sessions[token]["transport"].close()
        except:
            pass
        del sessions[token]
    return jsonify({"ok": True})

@app.route("/api/list", methods=["GET"])
def list_files():
    token = request.headers.get("X-Auth-Token")
    sftp, _ = get_sftp(token)
    if not sftp:
        return jsonify({"error": "Nicht eingeloggt"}), 401
    path = request.args.get("path", ".")
    try:
        items = []
        for attr in sftp.listdir_attr(path):
            is_dir = stat.S_ISDIR(attr.st_mode)
            items.append({"name": attr.filename, "is_dir": is_dir, "size": attr.st_size if not is_dir else 0, "modified": attr.st_mtime})
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        try:
            real_path = sftp.normalize(path)
        except:
            real_path = path
        return jsonify({"path": real_path, "items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/download", methods=["GET"])
def download_file():
    token = request.headers.get("X-Auth-Token")
    sftp, _ = get_sftp(token)
    if not sftp:
        return jsonify({"error": "Nicht eingeloggt"}), 401
    path = request.args.get("path")
    try:
        buf = io.BytesIO()
        sftp.getfo(path, buf)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=os.path.basename(path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/upload", methods=["POST"])
def upload_file():
    token = request.headers.get("X-Auth-Token")
    sftp, _ = get_sftp(token)
    if not sftp:
        return jsonify({"error": "Nicht eingeloggt"}), 401
    path = request.form.get("path", ".")
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "Keine Datei"}), 400
    try:
        remote_path = path.rstrip("/") + "/" + file.filename
        sftp.putfo(file.stream, remote_path)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/rename", methods=["POST"])
def rename():
    token = request.headers.get("X-Auth-Token")
    sftp, _ = get_sftp(token)
    if not sftp:
        return jsonify({"error": "Nicht eingeloggt"}), 401
    data = request.json
    try:
        sftp.rename(data.get("old_path"), data.get("new_path"))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/delete", methods=["POST"])
def delete():
    token = request.headers.get("X-Auth-Token")
    sftp, _ = get_sftp(token)
    if not sftp:
        return jsonify({"error": "Nicht eingeloggt"}), 401
    data = request.json
    try:
        if data.get("is_dir"):
            sftp.rmdir(data.get("path"))
        else:
            sftp.remove(data.get("path"))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/mkdir", methods=["POST"])
def mkdir():
    token = request.headers.get("X-Auth-Token")
    sftp, _ = get_sftp(token)
    if not sftp:
        return jsonify({"error": "Nicht eingeloggt"}), 401
    data = request.json
    try:
        sftp.mkdir(data.get("path"))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
