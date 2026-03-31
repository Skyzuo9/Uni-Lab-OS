#!/usr/bin/env python3
"""
Patch script: adds mesh-serving routes to layout.py on Ubuntu.
Run from /home/ubuntu/workspace/Uni-Lab-OS:
    python3 ~/Desktop/handover_layout_optimizer/patch_layout_routes.py
"""
import os, sys, json

LAYOUT_PY = "/home/ubuntu/workspace/Uni-Lab-OS/unilabos/app/web/routers/layout.py"
DEMO_DIR = "/home/ubuntu/workspace/Uni-Lab-OS/unilabos/services/layout_optimizer/demo"
DEVICE_MESH_DIR = "/home/ubuntu/workspace/Uni-Lab-OS/unilabos/device_mesh/devices"

# ── Code to append to layout.py ──
NEW_ROUTES = '''

# --- Mesh serving routes (3D model STL files) ---

@layout_router.get("/mesh_manifest")
async def mesh_manifest():
    """Return the mesh manifest JSON for 3D device rendering."""
    import json as _json
    manifest_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "services", "layout_optimizer", "demo", "mesh_manifest.json"
    )
    manifest_path = os.path.abspath(manifest_path)
    if not os.path.isfile(manifest_path):
        raise HTTPException(status_code=404, detail="mesh_manifest.json not found")
    from fastapi.responses import FileResponse
    return FileResponse(manifest_path, media_type="application/json")


@layout_router.get("/meshes/{device_id}/{filename:path}")
async def serve_device_mesh(device_id: str, filename: str):
    """Serve STL mesh files from device_mesh/devices/{device_id}/meshes/{filename}."""
    from fastapi.responses import FileResponse
    mesh_dir = "{DEVICE_MESH_DIR}"
    file_path = os.path.join(mesh_dir, device_id, "meshes", filename)
    file_path = os.path.abspath(file_path)
    if not file_path.startswith(os.path.abspath(mesh_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"Mesh file not found: {device_id}/meshes/{filename}")
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    media_type = "application/octet-stream"
    if ext == "stl":
        media_type = "application/sla"
    return FileResponse(file_path, media_type=media_type)
'''.replace("{DEVICE_MESH_DIR}", DEVICE_MESH_DIR)


def main():
    if not os.path.isfile(LAYOUT_PY):
        print(f"ERROR: {LAYOUT_PY} not found. Run this script on the Ubuntu system.")
        sys.exit(1)

    with open(LAYOUT_PY, "r") as f:
        content = f.read()

    if "mesh_manifest" in content:
        print("Routes already patched (mesh_manifest found). Skipping.")
        return

    # Ensure 'import os' is present
    if "import os" not in content:
        content = content.replace(
            "import logging",
            "import logging\nimport os",
            1
        )

    content += NEW_ROUTES

    with open(LAYOUT_PY, "w") as f:
        f.write(content)

    print(f"SUCCESS: Patched {LAYOUT_PY} with mesh_manifest and meshes routes.")
    print(f"  - GET /api/v1/layout/mesh_manifest")
    print(f"  - GET /api/v1/layout/meshes/{{device_id}}/{{filename}}")


if __name__ == "__main__":
    main()
