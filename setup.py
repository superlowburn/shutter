"""
py2app build configuration for Shutter.app

Build:
    python setup.py py2app        # standalone .app bundle
    python setup.py py2app -A     # alias mode (fast, for development)
"""

from setuptools import setup

APP = ["app.py"]

DATA_FILES = [
    ("resources", [
        "resources/menubar_icon.png",
        "resources/menubar_icon@2x.png",
    ]),
]

OPTIONS = {
    "argv_emulation": False,
    "emulate_shell_environment": True,
    "plist": {
        "CFBundleName": "Shutter",
        "CFBundleDisplayName": "Shutter",
        "CFBundleIdentifier": "com.superlowburn.shutter",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,
        "NSScreenCaptureUsageDescription": (
            "Shutter needs Screen Recording permission to capture your "
            "screen and provide AI tools with sanitized screen context. "
            "Screenshots are processed locally and never leave your machine."
        ),
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
    },
    "packages": [
        "rumps",
        "mlx", "mlx_vlm",
        "torch", "torchvision",
        "fastapi", "uvicorn", "fastmcp",
        "psutil",
        "PIL",
        "transformers", "huggingface_hub", "tokenizers", "safetensors",
        "starlette", "anyio", "httptools",
        "mcp",
    ],
    "includes": [
        "core", "api", "mcp_server", "redact",
        "Quartz", "Vision", "Foundation", "CoreML",
    ],
    "resources": ["core.py", "api.py", "mcp_server.py", "redact.py"],
    "iconfile": "resources/icon.icns",
}

setup(
    app=APP,
    name="Shutter",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
