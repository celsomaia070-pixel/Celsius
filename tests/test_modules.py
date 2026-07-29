"""Tests for company module catalog and suggestions."""

from core.modules import (
    MODULE_CHAT,
    MODULE_FINANCE,
    MODULE_INVENTORY,
    MODULE_SETTINGS,
    MODULE_SUPPLIERS,
    default_enabled_module_ids,
    normalize_module_ids,
    privacy_domains_for_segment,
    sidebar_modules,
    suggest_modules_for_company,
)


class TestModuleCatalog:
    def test_mandatory_modules_are_always_enabled(self):
        modules = normalize_module_ids([MODULE_INVENTORY])

        assert MODULE_CHAT in modules
        assert MODULE_SETTINGS in modules

    def test_unknown_modules_are_ignored(self):
        modules = normalize_module_ids(["unknown", MODULE_SUPPLIERS])

        assert "unknown" not in modules
        assert MODULE_SUPPLIERS in modules

    def test_default_modules_include_existing_ready_features(self):
        modules = default_enabled_module_ids()

        assert MODULE_CHAT in modules
        assert MODULE_SUPPLIERS in modules
        assert MODULE_INVENTORY in modules
        assert MODULE_SETTINGS in modules

    def test_sidebar_returns_enabled_ready_modules(self):
        modules = sidebar_modules([MODULE_CHAT, MODULE_FINANCE, MODULE_SETTINGS])
        module_ids = [module.id for module in modules]

        assert MODULE_CHAT in module_ids
        assert MODULE_SETTINGS in module_ids
        assert MODULE_FINANCE in module_ids


class TestModuleSuggestions:
    def test_suggests_modules_for_mechanic_shop(self):
        modules = suggest_modules_for_company("Oficina mecanica", "")

        assert MODULE_INVENTORY in modules
        assert MODULE_SUPPLIERS in modules
        assert MODULE_CHAT in modules
        assert MODULE_SETTINGS in modules

    def test_suggests_finance_from_needs(self):
        modules = suggest_modules_for_company("Outro", "organizar contas e financeiro")

        assert MODULE_FINANCE in modules

    def test_detects_sensitive_segments(self):
        assert "legal" in privacy_domains_for_segment("Escritorio de advocacia")
        assert "health" in privacy_domains_for_segment("Clinica odontologica")
