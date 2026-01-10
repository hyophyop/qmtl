import os
import re
import subprocess
from typing import Tuple


def define_env(env):
    @env.macro
    def nav_links():
        page = env.variables.get('page')
        if not page or not hasattr(page, 'file'):
            return ''
        base_dir = os.path.dirname(page.file.src_uri)
        def relpath(target):
            return os.path.relpath(target, base_dir) if base_dir else target
        parts = []
        parent = getattr(page, 'parent', None)
        if parent and hasattr(parent, 'file'):
            parts.append('**Parent:** [' + parent.title + '](' + relpath(parent.file.src_uri) + ')')
        children = getattr(page, 'children', None) or []
        children = [c for c in children if hasattr(c, 'file')]
        if children:
            child_links = ', '.join('[' + c.title + '](' + relpath(c.file.src_uri) + ')' for c in children)
            parts.append('**Children:** ' + child_links)
        siblings = []
        if parent and getattr(parent, 'children', None):
            siblings = [c for c in parent.children if c is not page and hasattr(c, 'file')]
        if siblings:
            sibling_links = ', '.join('[' + s.title + '](' + relpath(s.file.src_uri) + ')' for s in siblings)
            parts.append('**Related:** ' + sibling_links)
        return '\n\n'.join(parts)

    def _parse_origin_url(url: str) -> str | None:
        if not url:
            return None
        url = url.strip()
        if url.startswith((".", "/", "file:")):
            return None
        # git@github.com:owner/repo.git → https://github.com/owner/repo
        m = re.match(r"git@([^:]+):(.+?)\.git$", url)
        if m:
            return f"https://{m.group(1)}/{m.group(2)}"
        # https://github.com/owner/repo.git → https://github.com/owner/repo
        if url.endswith(".git"):
            return url[:-4]
        if "://" not in url:
            return None
        return url

    def _git_origin_https() -> str | None:
        try:
            out = subprocess.check_output([
                'git', 'config', '--get', 'remote.origin.url'
            ], stderr=subprocess.DEVNULL, text=True).strip()
            return _parse_origin_url(out)
        except Exception:
            return None

    def _repo_base_and_ref() -> Tuple[str, str]:
        # Prefer explicit overrides if set
        base = os.getenv('DOCS_CODE_BASE_URL')
        ref = os.getenv('DOCS_CODE_REF')

        # GitHub Actions environment
        server = os.getenv('GITHUB_SERVER_URL', 'https://github.com').rstrip('/')
        repo = os.getenv('GITHUB_REPOSITORY')  # owner/repo
        sha = os.getenv('GITHUB_SHA')
        ref_name = os.getenv('GITHUB_REF_NAME')
        github_ref = os.getenv('GITHUB_REF')  # e.g., refs/heads/main

        if not base and repo:
            base = f"{server}/{repo}"

        # Local repo fallback
        if not base:
            base = _git_origin_https() or 'https://github.com/hyophyop/qmtl'

        # Prefer a stable commit SHA when available; else branch; else HEAD
        resolved_ref = ref or sha or ref_name
        if not resolved_ref and github_ref:
            # refs/heads/main → main
            parts = github_ref.split('/')
            if len(parts) >= 3:
                resolved_ref = parts[-1]
        if not resolved_ref:
            resolved_ref = 'HEAD'

        return base.rstrip('/'), resolved_ref

    @env.macro
    def code_url(path: str, ref: str | None = None) -> str:
        base, default_ref = _repo_base_and_ref()
        use_ref = ref or default_ref
        return f"{base}/blob/{use_ref}/{path.lstrip('/')}"

    @env.macro
    def code_link(path: str, text: str | None = None, ref: str | None = None) -> str:
        url = code_url(path, ref=ref)
        label = text or path
        return f"[{label}]({url})"
