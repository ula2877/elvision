"""Diagnostic: print full widget tree of AddCameraDialog with stylesheet info."""
import sys
from PySide6.QtWidgets import QApplication, QWidget, QFormLayout, QLabel
from PySide6.QtCore import Qt
from app.ui.styles import generate_dark_theme
from app.ui.dialogs.add_camera import AddCameraDialog

app = QApplication(sys.argv)
app.setStyleSheet(generate_dark_theme())

dlg = AddCameraDialog()
dlg.show()
app.processEvents()

def dump(widget, depth=0):
    indent = "  " * depth
    cls = type(widget).__name__
    name = widget.objectName() or "(none)"
    g = widget.geometry()
    bg = widget.palette().color(widget.backgroundRole()).name()
    af = widget.autoFillBackground()
    ss = widget.styleSheet()
    vis = widget.isVisible()
    print(f"{indent}{cls} '{name}'  geo=({g.x()},{g.y()},{g.width()}x{g.height()})  palette_bg={bg}  autoFill={af}  visible={vis}")
    if ss:
        for line in ss.strip().split("\n"):
            print(f"{indent}  SS: {line.strip()}")

    layout = widget.layout()
    if layout:
        print(f"{indent}  Layout: {type(layout).__name__}")
        if isinstance(layout, QFormLayout):
            for row in range(layout.rowCount()):
                lbl_item = layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
                field_item = layout.itemAt(row, QFormLayout.ItemRole.FieldRole)
                if lbl_item and lbl_item.widget():
                    print(f"{indent}    Row {row} Label:")
                    dump(lbl_item.widget(), depth + 3)
                if field_item and field_item.widget():
                    print(f"{indent}    Row {row} Field:")
                    dump(field_item.widget(), depth + 3)
        else:
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item.widget():
                    dump(item.widget(), depth + 2)
                elif item.layout():
                    sub = item.layout()
                    print(f"{indent}    SubLayout: {type(sub).__name__}")
                    if isinstance(sub, QFormLayout):
                        for row in range(sub.rowCount()):
                            lbl_item = sub.itemAt(row, QFormLayout.ItemRole.LabelRole)
                            field_item = sub.itemAt(row, QFormLayout.ItemRole.FieldRole)
                            if lbl_item and lbl_item.widget():
                                dump(lbl_item.widget(), depth + 3)
                            if field_item and field_item.widget():
                                dump(field_item.widget(), depth + 3)
                    else:
                        for j in range(sub.count()):
                            si = sub.itemAt(j)
                            if si.widget():
                                dump(si.widget(), depth + 3)


print("=" * 70)
print("ADD CAMERA DIALOG - WIDGET TREE")
print("=" * 70)
dump(dlg)
print("=" * 70)

print("\n\nLABEL BACKGROUNDS:")
for lbl in dlg.findChildren(QLabel):
    palette_bg = lbl.palette().color(lbl.backgroundRole()).name()
    ss = lbl.styleSheet()
    parent_cls = type(lbl.parent()).__name__
    parent_name = lbl.parent().objectName() or "(none)"
    print(f"  QLabel '{lbl.text()[:30]}'  parent={parent_cls}'{parent_name}'  palette_bg={palette_bg}  own_ss='{ss[:80]}'")

sys.exit(0)
