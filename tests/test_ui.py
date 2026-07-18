"""Tests for UI components."""
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestTheme:
    def test_dark_scheme_exists(self):
        from ui.theme import DARK_SCHEME
        assert DARK_SCHEME is not None
        assert DARK_SCHEME.bg_primary == "#0D1117"

    def test_light_scheme_exists(self):
        from ui.theme import LIGHT_SCHEME
        assert LIGHT_SCHEME is not None
        assert LIGHT_SCHEME.bg_primary == "#FFFFFF"

    def test_get_stylesheet(self):
        from ui.theme import DARK_SCHEME, get_stylesheet
        css = get_stylesheet(DARK_SCHEME)
        assert "QMainWindow" in css
        assert "QPushButton" in css
        assert "#0D1117" in css


class TestSidebar:
    def test_sidebar_creation(self, qapp):
        from datetime import datetime

        from ui.sidebar import Sidebar

        sidebar = Sidebar()
        assert sidebar is not None

        # Test adding conversation
        item = sidebar.add_conversation("test-1", "Test Conversation", datetime.now())
        assert item is not None
        assert item.conv_id == "test-1"
        assert item.title == "Test Conversation"

    def test_sidebar_update(self, qapp):
        from datetime import datetime

        from ui.sidebar import Sidebar

        sidebar = Sidebar()
        sidebar.add_conversation("test-1", "Old Title", datetime.now())
        sidebar.update_conversation("test-1", "New Title")
        assert sidebar._conversations["test-1"].title == "New Title"

    def test_sidebar_remove(self, qapp):
        from datetime import datetime

        from ui.sidebar import Sidebar

        sidebar = Sidebar()
        sidebar.add_conversation("test-1", "Title", datetime.now())
        sidebar.remove_conversation("test-1")
        assert "test-1" not in sidebar._conversations


class TestCommandPalette:
    def test_palette_creation(self, qapp):
        from ui.command_palette import CommandPalette
        palette = CommandPalette()
        assert palette is not None
        assert len(palette._actions) > 0

    def test_add_custom_action(self, qapp):
        from ui.command_palette import CommandPalette
        palette = CommandPalette()
        initial_count = len(palette._actions)
        palette.add_action("test_action", "Test Action", "fa5s.test", "Ctrl+T")
        assert len(palette._actions) == initial_count + 1
        assert palette._actions[-1]["id"] == "test_action"


class TestChatView:
    def test_chat_view_creation(self, qapp):
        from ui.window import ModernChatView
        view = ModernChatView()
        assert view is not None

    def test_add_user_message(self, qapp):
        from ui.window import ModernChatView
        view = ModernChatView()
        view.add_user_message("Hello")
        assert len(view.messages) == 1
        assert view.messages[0] == ("user", "Hello")

    def test_add_assistant_message(self, qapp):
        from ui.window import ModernChatView
        view = ModernChatView()
        bubble = view.add_assistant_message("Hi there")
        assert len(view.messages) == 1
        assert view.messages[0] == ("assistant", "Hi there")

    def test_streaming(self, qapp):
        from ui.window import ModernChatView
        view = ModernChatView()
        bubble = view.start_streaming()
        view.append_streaming("Hello")
        view.append_streaming(" world")
        view.finish_streaming()
        assert "Hello world" in view.messages[-1][1]


class TestMessageBubble:
    def test_bubble_creation(self, qapp):
        from ui.window import MessageBubble
        bubble = MessageBubble("Test content", is_user=True)
        assert bubble.is_user
        assert bubble.content == "Test content"

    def test_bubble_rendering(self, qapp):
        from ui.window import MessageBubble
        bubble = MessageBubble("**Bold** and *italic* text")
        html = bubble.content_label.toHtml()
        # Qt renders markdown with span styles, not <i> tags
        assert "font-weight:700" in html  # Bold
        assert "font-style:italic" in html  # Italic


class TestModernInputArea:
    def test_input_area_creation(self, qapp):
        from ui.window import ModernInputArea
        area = ModernInputArea()
        assert area is not None

    def test_attachment_handling(self, qapp):
        from ui.window import ModernInputArea
        area = ModernInputArea()
        area.add_attachment("test.pdf")
        assert len(area._attachments) == 1
        area.add_attachment("test.png")
        assert len(area._attachments) == 2
        area._remove_attachment("test.pdf")
        assert len(area._attachments) == 1
        assert area._attachments[0] == "test.png"


class TestModernChatWindow:
    def test_window_creation(self, qapp):
        from ui.window import ModernChatWindow
        window = ModernChatWindow()
        assert window is not None
        assert window.windowTitle() == "Celsius"

    def test_new_conversation(self, qapp):
        from ui.window import ModernChatWindow
        window = ModernChatWindow()
        window._new_conversation()
        assert len(window.chat_view.messages) == 0
