from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path


def fail(message: str) -> None:
    raise RuntimeError(message)


def replace_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        fail(f"Expected one {label} marker, found {count}. The upstream patch needs review.")
    return content.replace(old, new, 1)


def replace_section(content: str, start: str, end: str, replacement: str, label: str) -> str:
    start_index = content.find(start)
    end_index = content.find(end, start_index + len(start))
    if start_index < 0 or end_index < 0:
        fail(f"Unable to find {label} section. The upstream patch needs review.")
    return content[:start_index] + replacement + content[end_index:]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_safely(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    with zipfile.ZipFile(archive) as zip_file:
        for member in zip_file.infolist():
            target = (destination / member.filename).resolve()
            try:
                target.relative_to(destination_root)
            except ValueError as exc:
                fail(f"Archive contains an unsafe path: {member.filename}")
                raise exc
        zip_file.extractall(destination)

    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        fail(f"Expected one archive root directory, found {len(roots)}")
    return roots[0]


def patch_backend(app_root: Path) -> None:
    main_path = app_root / "backend" / "main.py"
    content = main_path.read_text(encoding="utf-8")

    content = replace_once(
        content,
        "import tkinter as tk\nfrom tkinter import filedialog\n",
        "from docker_support import (\n"
        "    PathAccessError,\n"
        "    get_mixed_precision,\n"
        "    register_routes,\n"
        "    validate_output_name,\n"
        "    validate_path,\n"
        "    validate_training_config,\n"
        ")\n",
        "tkinter imports",
    )
    content = replace_once(
        content,
        "# Initialize tkinter for folder dialog\n"
        "root = tk.Tk()\n"
        "root.withdraw() # Hide main window\n"
        "root.attributes('-topmost', True) # Bring dialog to front\n",
        "register_routes(app)\n\n"
        "def require_path(path, roots, expected=\"any\", must_exist=True):\n"
        "    try:\n"
        "        return validate_path(path, roots, expected, must_exist)\n"
        "    except PathAccessError as exc:\n"
        "        raise HTTPException(status_code=400, detail=str(exc)) from exc\n\n"
        "def require_training_config(config):\n"
        "    try:\n"
        "        validate_training_config(config)\n"
        "    except PathAccessError as exc:\n"
        "        raise HTTPException(status_code=400, detail=str(exc)) from exc\n",
        "FastAPI initialization",
    )
    content = replace_once(
        content,
        "    global training_logs, training_process, training_active, training_stop_requested\n",
        "    global training_logs, training_process, training_active, training_stop_requested\n"
        "    require_training_config(config)\n    \n",
        "training validation",
    )
    content = replace_once(
        content,
        '        "--mixed_precision=bf16",\n',
        '        f"--mixed_precision={get_mixed_precision()}",\n',
        "mixed precision",
    )
    content = replace_section(
        content,
        'def run_dialog(kind: str, title: str):',
        '@app.get("/api/gpu-info")',
        '@app.get("/api/browse-folder")\n'
        'async def browse_folder():\n'
        '    raise HTTPException(status_code=410, detail="Use the Docker file browser")\n\n'
        '@app.get("/api/browse-file")\n'
        'async def browse_file():\n'
        '    raise HTTPException(status_code=410, detail="Use the Docker file browser")\n\n',
        "native file browser",
    )
    content = replace_once(
        content,
        "async def setup_scripts():\n    internal_scripts = os.path.join(os.path.dirname(__file__), \"sd-scripts\")",
        "async def setup_scripts():\n"
        "    raise HTTPException(status_code=409, detail=\"Dependencies are installed when the Docker image is built\")\n"
        "    internal_scripts = os.path.join(os.path.dirname(__file__), \"sd-scripts\")",
        "runtime setup guard",
    )
    content = replace_once(
        content,
        "async def list_images(path: str):\n    if not os.path.exists(path):",
        "async def list_images(path: str):\n"
        "    path = require_path(path, (\"datasets\",), \"directory\")\n"
        "    if not os.path.exists(path):",
        "dataset listing guard",
    )
    content = replace_once(
        content,
        "async def update_tags(update: TagUpdate):\n    # 'update.path' is the image path, we need the .txt path",
        "async def update_tags(update: TagUpdate):\n"
        "    update.path = require_path(update.path, (\"datasets\",), \"file\")\n"
        "    # Save tags to txt file",
        "tag update guard",
    )
    content = replace_once(
        content,
        "async def get_image(path: str):\n    if not os.path.exists(path):",
        "async def get_image(path: str):\n"
        "    path = require_path(path, (\"datasets\",), \"file\")\n"
        "    if not os.path.exists(path):",
        "image guard",
    )
    content = replace_once(
        content,
        "async def run_tagger(config: TaggerConfig):\n    global tagging_logs",
        "async def run_tagger(config: TaggerConfig):\n"
        "    config.path = require_path(config.path, (\"datasets\",), \"directory\")\n"
        "    global tagging_logs",
        "tagger guard",
    )
    content = replace_once(
        content,
        "async def convert_to_comfy(config: TrainingConfig):\n    script_path = os.path.join(os.path.dirname(__file__), \"sd-scripts\")",
        "async def convert_to_comfy(config: TrainingConfig):\n"
        "    config.output_dir = require_path(config.output_dir, (\"output\",), \"directory\")\n"
        "    try:\n"
        "        validate_output_name(config.name)\n"
        "    except PathAccessError as exc:\n"
        "        raise HTTPException(status_code=400, detail=str(exc)) from exc\n"
        "    script_path = os.path.join(os.path.dirname(__file__), \"sd-scripts\")",
        "conversion guard",
    )
    main_path.write_text(content, encoding="utf-8", newline="\n")


def patch_frontend(app_root: Path) -> None:
    html_path = app_root / "frontend" / "index.html"
    content = html_path.read_text(encoding="utf-8")
    content = replace_once(
        content,
        "</head>",
        '    <link rel="stylesheet" href="file_browser.css?v=docker-1">\n</head>',
        "frontend stylesheet",
    )
    content = replace_once(
        content,
        '<script src="app.js?v=6.0"></script>',
        '<script src="app.js?v=docker-2"></script>\n    <script src="file_browser.js?v=docker-1"></script>',
        "frontend script",
    )
    html_path.write_text(content, encoding="utf-8", newline="\n")

    app_path = app_root / "frontend" / "app.js"
    content = app_path.read_text(encoding="utf-8")
    content = replace_once(
        content,
        "        } else {\n"
        "            consoleOut.innerHTML += `<span style=\"color: #ef4444;\">Error: ${data.message}</span>`;\n"
        "        }\n"
        "    } catch (e) {\n"
        "        consoleOut.innerHTML += `<span style=\"color: #ef4444;\">Error: ${e.message}</span>`;\n"
        "    }\n"
        "}\n\n"
        "function setStopButtonVisible(visible) {",
        "        } else {\n"
        "            appendTrainingError(consoleOut, getApiErrorMessage(data, `Request failed (${response.status})`));\n"
        "        }\n"
        "    } catch (e) {\n"
        "        appendTrainingError(consoleOut, e instanceof Error ? e.message : String(e));\n"
        "    }\n"
        "}\n\n"
        "function getApiErrorMessage(data, fallback = 'Unknown error') {\n"
        "    if (typeof data?.message === 'string' && data.message) return data.message;\n"
        "    if (typeof data?.detail === 'string' && data.detail) return data.detail;\n"
        "    if (Array.isArray(data?.detail)) {\n"
        "        const messages = data.detail.map(item => {\n"
        "            const location = Array.isArray(item?.loc) ? item.loc.filter(part => part !== 'body').join('.') : '';\n"
        "            return `${location ? location + ': ' : ''}${item?.msg || JSON.stringify(item)}`;\n"
        "        });\n"
        "        if (messages.length) return messages.join('; ');\n"
        "    }\n"
        "    return fallback;\n"
        "}\n\n"
        "function appendTrainingError(consoleOut, message) {\n"
        "    const error = document.createElement('span');\n"
        "    error.style.color = '#ef4444';\n"
        "    error.textContent = `Error: ${message}`;\n"
        "    consoleOut.appendChild(error);\n"
        "}\n\n"
        "function setStopButtonVisible(visible) {",
        "training error handling",
    )
    app_path.write_text(content, encoding="utf-8", newline="\n")


def materialize(archive: Path, lock_path: Path, output: Path) -> None:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if archive.name != lock["archive"] and archive.name != "upstream.zip":
        fail(f"Archive name does not match lock: {archive.name}")
    actual_hash = sha256(archive)
    if actual_hash.lower() != lock["sha256"].lower():
        fail(f"Archive SHA-256 mismatch: expected {lock['sha256']}, got {actual_hash}")

    staging = output.parent / f".{output.name}-staging"
    if staging.exists():
        shutil.rmtree(staging)
    if output.exists():
        shutil.rmtree(output)
    root = extract_safely(archive, staging)
    shutil.move(str(root), str(output))
    shutil.rmtree(staging)

    overlay = Path(__file__).resolve().parent / "app"
    shutil.copy2(overlay / "docker_support.py", output / "backend" / "docker_support.py")
    shutil.copy2(overlay / "file_browser.js", output / "frontend" / "file_browser.js")
    shutil.copy2(overlay / "file_browser.css", output / "frontend" / "file_browser.css")
    patch_backend(output)
    patch_frontend(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    materialize(args.archive.resolve(), args.lock.resolve(), args.output.resolve())
    print(f"Materialized Anima LoRA Factory at {args.output}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
