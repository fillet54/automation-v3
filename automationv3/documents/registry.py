"""Rendering registry adapter between framework.plugins and documents/"""

from docutils.parsers.rst import directives, roles

from ..framework import plugins
from . import core, template


class DocumentRegistry:
    """Connects framework.plugins.PluginRegistry to documents.core and
    documents.template, with atomic snapshot/rollback."""

    def builtins(self, kind):
        if kind == "directive":
            return core.RESOLVERS
        if kind == "role":
            return core.ROLE_VALUES
        if kind == "filter":
            return {*template.FILTERS, *template.BUILTIN_FILTERS}
        return ()

    def register_directive(self, name, resolver, option_spec=None, arguments=False):
        core.directive(name, resolver, option_spec, arguments)

    def register_role(self, name, value):
        core.role(name, value)

    def register_filter(self, name, fn):
        template.FILTERS[name] = fn
        template.Snippets._envs.clear()

    def register_snippets(self, folder):
        template.register_folder(folder)

    def snapshot(self):
        return (
            set(core.RESOLVERS),
            set(core.ROLE_VALUES),
            set(template.FILTERS),
            list(template.Snippets.plugin_folders),
        )

    def restore(self, snap):
        resolvers, role_names, filters, folders = snap
        # out of docutils too, or the name still parses and then has no resolver
        for name in set(core.RESOLVERS) - resolvers:
            core.RESOLVERS.pop(name, None)
            directives._directives.pop(name, None)
        for name in set(core.ROLE_VALUES) - role_names:
            core.ROLE_VALUES.pop(name, None)
            roles._roles.pop(name, None)
        for name in set(template.FILTERS) - filters:
            template.FILTERS.pop(name, None)
        template.Snippets.plugin_folders[:] = folders
        template.Snippets._envs.clear()


plugins.set_rendering_registry(DocumentRegistry())
