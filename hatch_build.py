"""Custom hatch build hook: builds frontend before wheel packaging."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class FrontendBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        frontend_dir = Path(self.root) / "llm_pipeline" / "ui" / "frontend"
        dist_dir = frontend_dir / "dist"

        if dist_dir.exists() and (dist_dir / "index.html").exists():
            self.app.display_info("Frontend dist/ already exists, skipping build")
            return

        if not (frontend_dir / "package.json").exists():
            self.app.display_warning("No frontend/package.json found, skipping build")
            return

        use_shell = sys.platform == "win32"

        self.app.display_info("Installing frontend dependencies (npm ci)...")
        subprocess.run(
            ["npm", "ci"],
            cwd=str(frontend_dir),
            check=True,
            shell=use_shell,
        )

        self.app.display_info("Building frontend (npm run build)...")
        subprocess.run(
            ["npm", "run", "build"],
            cwd=str(frontend_dir),
            check=True,
            shell=use_shell,
        )

        if not (dist_dir / "index.html").exists():
            msg = "Frontend build did not produce dist/index.html"
            raise RuntimeError(msg)

        self.app.display_info("Frontend build complete")
