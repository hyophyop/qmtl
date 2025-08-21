import os

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
