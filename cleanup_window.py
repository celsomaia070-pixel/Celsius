import re

with open("E:/PythonProjectCELSIUS/ui/window.py", encoding="utf-8") as f:
    content = f.read()

# Remove _on_model_list_loaded, _on_model_changed, _on_model_loaded, _on_model_load_error
# These are between _select_model_in_combo and _populate_model_combo
pattern = (
    r"    def _on_model_list_loaded\(self, models: list\):.*?(?=\n    def _populate_model_combo)"
)
content = re.sub(pattern, "", content, flags=re.DOTALL)

# Remove _on_input_mode_changed method
pattern2 = (
    r"    def _on_input_mode_changed\(self, mode_id: str\):.*?(?=\n    # User message handler)"
)
content = re.sub(pattern2, "", content, flags=re.DOTALL)

# Remove _populate_model_combo and _select_model_in_combo methods since model_combo no longer exists
pattern3 = r"    def _populate_model_combo\(self\):.*?(?=\n    def )"
content = re.sub(pattern3, "", content, flags=re.DOTALL)

pattern4 = r"    def _select_model_in_combo\(self, model_id: str\) -> None:.*?(?=\n    def )"
content = re.sub(pattern4, "", content, flags=re.DOTALL)

# Remove COMBO_MODEL_AUTO constant since no longer used
content = re.sub(
    r'#: Id sentinel para a opcao "Auto \(JEV\)" no seletor de modelos\.\nCOMBO_MODEL_AUTO = "__auto__"\n\n',
    "",
    content,
)

with open("E:/PythonProjectCELSIUS/ui/window.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
