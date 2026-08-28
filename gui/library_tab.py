"""乐谱库页(对齐 Web 设计稿):列表 + 刷新/去演奏/删除。"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.theme import BRAND, INK_2, STATE_INFO, STATE_SUCCESS


class LibraryTab(QWidget):
    go_play = pyqtSignal(int)

    def __init__(self, db):
        super().__init__()
        self._db = db
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("已保存乐谱")
        title.setObjectName("PageTitle")
        self.count_label = QLabel("")
        self.count_label.setObjectName("PageSub")
        header.addWidget(title)
        header.addWidget(self.count_label)
        header.addStretch(1)
        root.addLayout(header)

        desc = QLabel("保存过的乐谱无需再次上传,可直接演奏")
        desc.setObjectName("SectionSubtitle")
        root.addWidget(desc)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("BtnSecondary")
        refresh_btn.clicked.connect(self.refresh)
        play_btn = QPushButton("去演奏")
        play_btn.setObjectName("BtnPrimary")
        play_btn.clicked.connect(self._go_play_selected)
        del_btn = QPushButton("删除选中")
        del_btn.setObjectName("BtnDanger")
        del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(play_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "名称", "来源", "默认BPM", "保存时间"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(lambda r, c: self._go_play_row(r))
        root.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        scores = self._db.list_scores()
        self.count_label.setText(f"共 {len(scores)} 首")
        self.table.setRowCount(0)
        for s in scores:
            row = self.table.rowCount()
            self.table.insertRow(row)
            id_item = QTableWidgetItem(str(s["id"]))
            id_item.setForeground(QColor(INK_2))
            name_item = QTableWidgetItem(s["name"])
            name_item.setForeground(QColor("#EDEDF2"))
            src = s["source_type"] or "-"
            src_item = QTableWidgetItem("图片" if src == "image" else "文档" if src == "document" else "-")
            src_item.setForeground(QColor(STATE_INFO if src == "image" else STATE_SUCCESS))
            bpm_item = QTableWidgetItem(str(s["bpm_default"]))
            bpm_item.setForeground(QColor(BRAND))
            date_item = QTableWidgetItem(s["created_at"])
            date_item.setForeground(QColor(INK_2))
            for col, item in enumerate((id_item, name_item, src_item, bpm_item, date_item)):
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()

    def _selected_id(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "提示", "请先在列表中选择一条乐谱")
            return None
        row = sorted(rows)[0]
        return int(self.table.item(row, 0).text())

    def _go_play_row(self, row):
        self.go_play.emit(int(self.table.item(row, 0).text()))

    def _go_play_selected(self):
        score_id = self._selected_id()
        if score_id is not None:
            self.go_play.emit(score_id)

    def _delete_selected(self):
        score_id = self._selected_id()
        if score_id is None:
            return
        self._db.delete_score(score_id)
        self.refresh()