"""
Plugin loader for DataSphere generators.

Third-party generators are discovered via Python entry_points:
    [project.entry-points."datasphere.generators"]
    my_generator = "my_package.generator:MyGenerator"

Built-in generators are always available regardless.
"""
from __future__ import annotations
import importlib
import logging
from typing import Any

_log = logging.getLogger(__name__)

# Entry point group name
_EP_GROUP = "datasphere.generators"

# Built-in generators (always available)
_BUILTIN_GENERATORS = {
    "dbt": "datasphere.generators.dbt_project:DbtProjectGenerator",
    "airflow": "datasphere.generators.airflow_dag:AirflowDagGenerator",
    "dagster": "datasphere.generators.dagster_job:DagsterJobGenerator",
    "prefect": "datasphere.generators.prefect_flow:PrefectFlowGenerator",
    "terraform": "datasphere.generators.terraform:TerraformGenerator",
    "lineage": "datasphere.generators.lineage:LineageGenerator",
}


class GeneratorPlugin:
    """Wrapper around a loaded generator class."""

    def __init__(self, name: str, cls: type, source: str = "builtin"):
        self.name = name
        self.cls = cls
        self.source = source  # "builtin" or "plugin"
        self._instance = None

    @property
    def instance(self):
        if self._instance is None:
            self._instance = self.cls()
        return self._instance

    def generate(self, *args, **kwargs):
        return self.instance.generate(*args, **kwargs)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "class": self.cls.__name__,
            "module": self.cls.__module__,
            "source": self.source,
            "description": (self.cls.__doc__ or "").strip().split("\n")[0],
        }


class PluginRegistry:
    """Registry of all available generator plugins."""

    def __init__(self):
        self._plugins: dict[str, GeneratorPlugin] = {}
        self._loaded = False

    def load(self) -> None:
        """Load built-in generators and discover installed plugins."""
        if self._loaded:
            return

        # Load built-ins
        for name, dotted_path in _BUILTIN_GENERATORS.items():
            try:
                module_path, class_name = dotted_path.rsplit(":", 1)
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                self._plugins[name] = GeneratorPlugin(name, cls, source="builtin")
            except Exception as exc:
                _log.warning("builtin_plugin_load_failed name=%s error=%s", name, exc)

        # Discover installed plugins via entry_points
        try:
            from importlib.metadata import entry_points
            eps = entry_points(group=_EP_GROUP)
            for ep in eps:
                try:
                    cls = ep.load()
                    plugin = GeneratorPlugin(ep.name, cls, source="plugin")
                    self._plugins[ep.name] = plugin
                    _log.info("plugin_loaded name=%s class=%s", ep.name, cls.__name__)
                except Exception as exc:
                    _log.warning("plugin_load_failed name=%s error=%s", ep.name, exc)
        except Exception as exc:
            _log.debug("entry_points_discovery_failed error=%s", exc)

        self._loaded = True
        _log.info("plugin_registry_ready count=%d", len(self._plugins))

    def get(self, name: str) -> GeneratorPlugin | None:
        if not self._loaded:
            self.load()
        return self._plugins.get(name)

    def list_all(self) -> list[GeneratorPlugin]:
        if not self._loaded:
            self.load()
        return list(self._plugins.values())

    def list_names(self) -> list[str]:
        return [p.name for p in self.list_all()]

    def register(self, name: str, cls: type, source: str = "plugin") -> GeneratorPlugin:
        """Manually register a generator (useful for testing)."""
        plugin = GeneratorPlugin(name, cls, source=source)
        self._plugins[name] = plugin
        return plugin

    def unregister(self, name: str) -> bool:
        return bool(self._plugins.pop(name, None))

    def reload(self) -> None:
        """Force re-discovery of plugins."""
        self._plugins.clear()
        self._loaded = False
        self.load()


# Module-level singleton
plugin_registry = PluginRegistry()
