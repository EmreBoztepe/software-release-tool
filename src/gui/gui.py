import sys
from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal
import traceback
from a2l.main_a2l import build_symbol_map, process_a2l
from elftools.elf.elffile import ELFFile
from t32 import t32
from vision import ati_vision
import os

from PySide6.QtCore import Qt, QDateTime, QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QGroupBox,
    QMessageBox,
    QProgressBar,
    QComboBox
)
@dataclass
class UiConfig:
    a2l_path: str = ""
    s19_path: str = ""
    boot_path: str = ""
    elf_path: str = ""
    addressed_a2l_path: str = ""
    output_dir: str = ""

class A2LAddressWorker(QObject):
    log = Signal(str)
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(str)      # çıktı A2L path
    failed = Signal(str)        # error text

    def __init__(self, a2l_in: str, elf_path: str, out_dir: str, svn_number: str, selected_project: str):
        super().__init__()
        self.a2l_in = Path(a2l_in)
        self.elf_path = Path(elf_path)
        self.out_dir = Path(out_dir)
        self.selected_project = selected_project
        self.svn_num = svn_number

    def run(self):
        try:
            self.status.emit("A2L addressing started")
            self.progress.emit(5)

            # Output isimleri
            if self.selected_project == "project1": 
                name = "pj1"
            if self.selected_project == "project2": 
                name = "pj2"
            
            out_a2l = self.out_dir / f"{name}_ecu_{self.svn_num}.a2l"
            out_csv = self.out_dir / f"{name}_ecu_{self.svn_num}.csv"

            self.log.emit(f"Input A2L : {self.a2l_in}")
            self.log.emit(f"Input ELF : {self.elf_path}")
            self.log.emit(f"Output A2L: {out_a2l}")
            self.log.emit(f"Output CSV: {out_csv}")
            self.progress.emit(10)

            # ELF aç + symbol map
            self.status.emit("Loading ELF & symbols")
            with self.elf_path.open("rb") as f:
                elf = ELFFile(f)
                symmap = build_symbol_map(elf)
                self.progress.emit(40)

                # A2L işlem
                self.status.emit("Resolving ECU addresses in A2L")
                process_a2l(self.a2l_in, out_a2l, elf, symmap, out_csv)
                self.progress.emit(100)

            self.status.emit("Done")
            self.finished.emit(str(out_a2l))

        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")


class Trace32Worker(QObject):
    log = Signal(str)
    status = Signal(str)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, elf_path: str, boot_path: str):
        super().__init__()
        self.elf_path = elf_path
        self.boot_path = boot_path

    def run(self):
        try:
            self.status.emit("TRACE32 flashing started")
            self.log.emit(f"TRACE32: flashing BOOT -> {self.boot_path}")
            self.log.emit(f"TRACE32: flashing ELF -> {self.elf_path}")

            t32.run_flash(self.elf_path, self.boot_path)

            self.status.emit("TRACE32 flashing done")
            self.finished.emit()

        except Exception as e:
            self.failed.emit(str(e))

class VisionWorker(QObject):
    log = Signal(str)
    status = Signal(str)
    finished = Signal()
    failed = Signal(str)

    def __init__(self,a2l_path,s19_path: str):
        super().__init__()
        self.a2l_path = a2l_path
        self.s19_path = s19_path


    def run(self):
        try:
            self.status.emit("Vision is starting...")
            self.log.emit(f"Vision S19-> {self.s19_path}")
            self.log.emit(f"Vision S19-> {self.a2l_path}")

            ati_vision.ecu_connection_on_vision(self.a2l_path,self.s19_path)

            self.status.emit("Vision operation finished.")
            self.finished.emit()

        except Exception as e:
            self.failed.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Software Release Tool")
        self.setWindowIcon(QIcon('logo.jpg'))
        self.resize(1100, 650)
        self.pending_cfg = None            # mevcut akış config’i
        self.addressed_a2l_path = None     # output dir’de üretilen addressed a2l
        self.selected_project = None       # kullanıcının ekranda sectigi proje 
        # Kalıcı ayarlar (son kullanılan path'leri hatırlasın)
        self.settings = QSettings("IgnisTools", "VisionIntegrationGUI")

        root = QWidget()  
        # Ana pencerenin içeriğini taşıyacak boş bir container (widget) oluşturulur.

        self.setCentralWidget(root)
        # QMainWindow tek bir central widget kabul eder.
        # Butonlar, textbox'lar ve tüm ana içerik bu widget'ın içinde yer alır.

        # --- Sol panel: Input alanları
        self.a2l_edit = QLineEdit()
        self.a2l_btn = QPushButton("Browse...")
        self.a2l_btn.clicked.connect(lambda: self._pick_file(self.a2l_edit, "A2L Files (*.a2l);;All Files (*.*)"))

        self.s19_edit = QLineEdit()
        self.s19_btn = QPushButton("Browse...")
        self.s19_btn.clicked.connect(lambda: self._pick_file(self.s19_edit, "S-Record Files (*.s19);;All Files (*.*)"))

        self.boot_edit = QLineEdit()
        self.boot_btn = QPushButton("Browse...")
        self.boot_btn.clicked.connect(lambda: self._pick_file(self.boot_edit, "S-Record Files (*.s19);;All Files (*.*)"))

        self.elf_edit = QLineEdit()
        self.elf_btn = QPushButton("Browse...")
        self.elf_btn.clicked.connect(lambda: self._pick_file(self.elf_edit, "Elf File (*.elf);"))

        self.out_edit = QLineEdit()
        self.out_btn = QPushButton("Browse...")
        self.out_btn.clicked.connect(lambda: self._pick_dir(self.out_edit))

        self.svn_num = QLineEdit()

        self.project_combo = QComboBox()
        self.project_combo.addItem("project1")
        self.project_combo.addItem("project2")
        self.project_combo.addItem("project3")
        self.project_combo.addItem("project4")

        input_group = QGroupBox("Inputs")
        input_layout = QGridLayout()
        input_layout.setColumnStretch(1, 1)

        input_layout.addWidget(QLabel("A2L Path:"), 0, 0)
        input_layout.addWidget(self.a2l_edit, 0, 1)
        input_layout.addWidget(self.a2l_btn, 0, 2)

        input_layout.addWidget(QLabel("S19 Path:"), 1, 0)
        input_layout.addWidget(self.s19_edit, 1, 1)
        input_layout.addWidget(self.s19_btn, 1, 2)

        input_layout.addWidget(QLabel("Boot Path"), 2, 0)
        input_layout.addWidget(self.boot_edit, 2, 1)
        input_layout.addWidget(self.boot_btn, 2, 2)

        input_layout.addWidget(QLabel("ELF Path:"), 3, 0)
        input_layout.addWidget(self.elf_edit, 3, 1)
        input_layout.addWidget(self.elf_btn, 3, 2)

        input_layout.addWidget(QLabel("Output Dir:"), 4, 0)
        input_layout.addWidget(self.out_edit, 4, 1)
        input_layout.addWidget(self.out_btn, 4, 2)

        input_layout.addWidget(QLabel("Svn Number:"), 5, 0)
        input_layout.addWidget(self.svn_num, 5, 1)
        
        input_layout.addWidget(QLabel("Select Project"),10 , 0)
        input_layout.addWidget(self.project_combo,10,1)

        opts_row = QHBoxLayout()
        opts_row.addStretch(1)
        input_layout.addLayout(opts_row, 5, 1)

        input_group.setLayout(input_layout)

        # Butonlar
        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(self.on_run_clicked)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.run_btn)
        btn_row.addStretch(1)

        left_col = QVBoxLayout()
        left_col.addWidget(input_group)
        left_col.addLayout(btn_row)
        left_col.addStretch(1)

        left_panel = QWidget()
        left_panel.setLayout(left_col)

        # --- Sağ panel: Progress + Status + Log
        self.status_label = QLabel("Status: Idle")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.NoWrap)

        self.copy_log_btn = QPushButton("Copy Log")
        self.copy_log_btn.clicked.connect(self.on_copy_log)

        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.log.clear)

        log_btn_row = QHBoxLayout()
        log_btn_row.addWidget(self.clear_log_btn)
        log_btn_row.addWidget(self.copy_log_btn)
        log_btn_row.addStretch(1)

        right_col = QVBoxLayout()
        right_col.addWidget(self.status_label)
        right_col.addWidget(self.progress)
        right_col.addWidget(QLabel("Log:"))
        right_col.addWidget(self.log, 1)
        right_col.addLayout(log_btn_row)

        right_panel = QWidget()
        right_panel.setLayout(right_col)

        # --- Ana yerleşim: 2 kolon
        main_row = QHBoxLayout()
        main_row.addWidget(left_panel, 0)
        main_row.addWidget(right_panel, 1)

        root.setLayout(main_row)

        # Son ayarları yükle
        self._restore_settings()
        self._log_info("GUI is ready. Pick the files and click to Run button.")

    # -------------------------
    # UI helpers
    # -------------------------
    def _log_info(self, msg: str) -> None:
        ts = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        self.log.appendPlainText(f"[{ts}] {msg}")

    def _set_status(self, msg: str) -> None:
        self.status_label.setText(f"Status: {msg}")

    def _pick_file(self, target_edit: QLineEdit, filter_str: str) -> None:
        start_dir = self._best_start_dir()
        path, _ = QFileDialog.getOpenFileName(self, "Select file", start_dir, filter_str)
        if path:
            target_edit.setText(path)
            self._save_settings()  # her seçimde kaydet

    def _pick_dir(self, target_edit: QLineEdit) -> None:
        start_dir = self._best_start_dir()
        path = QFileDialog.getExistingDirectory(self, "Select output directory", start_dir)
        if path:
            target_edit.setText(path)
            self._save_settings()

    def _best_start_dir(self) -> str:
        # Önce output dir, yoksa base vpj, yoksa current
        for candidate in (self.out_edit.text(), self.elf_edit.text(), self.a2l_edit.text(), self.s19_edit.text()):
            if candidate:
                p = Path(candidate)
                if p.is_dir():
                    return str(p)
                if p.is_file():
                    return str(p.parent)
        return str(Path.cwd())

    def _validate_inputs(self) -> tuple[bool, str]:
        a2l = self.a2l_edit.text().strip()
        s19 = self.s19_edit.text().strip()
        elf = self.elf_edit.text().strip()
        outdir = self.out_edit.text().strip()
        svn_text  = self.svn_num.text().strip()
        if not a2l or not Path(a2l).is_file():
            return False, "A2L dosyasi seçili değil veya bulunamadi."
        if not s19 or not Path(s19).is_file():
            return False, "S19 dosyası seçili değil veya bulunamadi."
        if not elf or not Path(elf).is_file():
            return False, "Elf seçili değil veya bulunamadi."
        if not outdir or not Path(outdir).is_dir():
            return False, "Output directory seçili değil veya bulunamadı."
        if not svn_text:
            return False, "SVN ID girilmedi."
        
        try:
            svn_num = int(svn_text)
        except ValueError:
            return False, "SVN ID sayısal bir değer olmalı."

        if svn_num < 0:
            return False, "SVN ID negatif olamaz."
    
        return True, ""

    # -------------------------
    # Button handlers
    # -------------------------
    def on_run_clicked(self) -> None:
        ok, err = self._validate_inputs()
        if not ok:
            QMessageBox.warning(self, "Input validation", err)
            self._log_info(f"VALIDATION ERROR: {err}")
            self._set_status("Validation error")
            return

        cfg = self._collect_config()
        self._save_settings()

        # Log
        self.selected_project = self.project_combo.currentText()
        svn_number =  int(self.svn_num.text())
        self._log_info(f"Svn number:,{svn_number}")
        self._log_info("Run clicked -> A2L addressing is starting...")
        self._log_info(f"A2L: {cfg.a2l_path}")
        self._log_info(f"ELF: {cfg.elf_path}")
        self._log_info(f"Output Dir: {cfg.output_dir}")

        # Backend
        self._start_a2l_addressing(cfg)


    def on_copy_log(self) -> None:
        QApplication.clipboard().setText(self.log.toPlainText())
        self._log_info("Log clipboard'a kopyalandı.")

    def on_save_preset(self) -> None:
        preset_path, _ = QFileDialog.getSaveFileName(self, "Save preset", self._best_start_dir(), "JSON Files (*.json)")
        if not preset_path:
            return
        cfg = self._collect_config()
        try:
            import json
            with open(preset_path, "w", encoding="utf-8") as f:
                json.dump(cfg.__dict__, f, ensure_ascii=False, indent=2)
            self._log_info(f"Preset kaydedildi: {preset_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save preset failed", str(e))
            self._log_info(f"ERROR saving preset: {e}")

    def on_load_preset(self) -> None:
        preset_path, _ = QFileDialog.getOpenFileName(self, "Load preset", self._best_start_dir(), "JSON Files (*.json)")
        if not preset_path:
            return
        try:
            import json
            with open(preset_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._apply_config(UiConfig(**data))
            self._log_info(f"Preset yüklendi: {preset_path}")
            self._save_settings()
        except Exception as e:
            QMessageBox.critical(self, "Load preset failed", str(e))
            self._log_info(f"ERROR loading preset: {e}")

    # -------------------------
    # Config / Settings
    # -------------------------
    def _collect_config(self) -> UiConfig:
        return UiConfig(
            a2l_path=self.a2l_edit.text().strip(),
            s19_path=self.s19_edit.text().strip(),
            boot_path=self.boot_edit.text().strip(),
            elf_path=self.elf_edit.text().strip(),
            output_dir=self.out_edit.text().strip(),
        )

    def _apply_config(self, cfg: UiConfig) -> None:
        self.a2l_edit.setText(cfg.a2l_path)
        self.s19_edit.setText(cfg.s19_path)
        self.elf_edit.setText(cfg.elf_path)
        self.out_edit.setText(cfg.output_dir)

    def _save_settings(self) -> None:
        cfg = self._collect_config()
        self.settings.setValue("a2l_path", cfg.a2l_path)
        self.settings.setValue("s19_path", cfg.s19_path)
        self.settings.setValue("elf_path", cfg.elf_path)
        self.settings.setValue("output_dir", cfg.output_dir)

    def _restore_settings(self) -> None:
        cfg = UiConfig(
            a2l_path=self.settings.value("a2l_path", "", type=str),
            s19_path=self.settings.value("s19_path", "", type=str),
            elf_path=self.settings.value("elf_path", "", type=str),
            output_dir=self.settings.value("output_dir", "", type=str),
        )
        self._apply_config(cfg)

    def _start_a2l_addressing(self, cfg: UiConfig) -> None:
        # UI state
        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        self._set_status("Starting A2L addressing...")

        # Thread + Worker
        self.thread = QThread(self)
        self.worker = A2LAddressWorker(cfg.a2l_path, cfg.elf_path, cfg.output_dir, self.svn_num.text(),self.selected_project)
        self.worker.moveToThread(self.thread)

        # Signals
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._log_info)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self._set_status)

        self.worker.finished.connect(self._on_a2l_done)
        self.worker.failed.connect(self._on_a2l_failed)

        # Cleanup
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def _on_vision_done(self):
        self._log_info("VISION OK")
        self._set_status("Ready")
        self._pending_cfg = None
        self.run_btn.setEnabled(True)

    def _on_vision_failed(self, err: str):
        self._log_info("VISION FAILED")
        self._log_info(err)
        QMessageBox.critical(self, "VISION Error", "Vision operation failed")
        self._set_status("Vision failed")
        self._pending_cfg = None
        self.run_btn.setEnabled(True)

    def _create_vision_package(self, a2l_path, s19_path: str):
        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        self._set_status("Starting vision...")

        self.vision_thread = QThread(self)
        self.vison_worker = VisionWorker(a2l_path,s19_path)
        self.vison_worker.moveToThread(self.vision_thread)

        # thread → worker
        self.vision_thread.started.connect(self.vison_worker.run)

        # worker → GUI
        self.vison_worker.log.connect(self._log_info)
        self.vison_worker.status.connect(self._set_status)
        self.vison_worker.finished.connect(self._on_vision_done)
        self.vison_worker.failed.connect(self._on_vision_failed)

        # cleanup
        self.vison_worker.finished.connect(self.vision_thread.quit)
        self.vison_worker.failed.connect(self.vision_thread.quit)
        self.vision_thread.finished.connect(self.vison_worker.deleteLater)
        self.vision_thread.finished.connect(self.vision_thread.deleteLater)

        self.vision_thread.start()

    def _start_trace32_flash(self, elf_path: str, boot_path: str):
        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        self._set_status("Starting TRACE32 flash...")

        self.t32_thread = QThread(self)
        self.t32_worker = Trace32Worker(elf_path, boot_path)
        self.t32_worker.moveToThread(self.t32_thread)

        # thread → worker
        self.t32_thread.started.connect(self.t32_worker.run)

        # worker → GUI
        self.t32_worker.log.connect(self._log_info)
        self.t32_worker.status.connect(self._set_status)
        self.t32_worker.finished.connect(self._on_t32_done)
        self.t32_worker.failed.connect(self._on_t32_failed)

        # cleanup
        self.t32_worker.finished.connect(self.t32_thread.quit)
        self.t32_worker.failed.connect(self.t32_thread.quit)
        self.t32_thread.finished.connect(self.t32_worker.deleteLater)
        self.t32_thread.finished.connect(self.t32_thread.deleteLater)

        self.t32_thread.start()
        
    def _on_a2l_done(self, out_a2l_path: str) -> None:
        self._log_info(f"A2L addressing OK. Output: {out_a2l_path}")
        self._set_status("A2L addressing completed")

        cfg = self._collect_config()

        # önemli: bu ORIGINAL A2L değil, addressed A2L
        cfg.addressed_a2l_path = out_a2l_path

        self._pending_cfg = cfg

        # Trace32’ye geç
        self._start_trace32_flash(cfg.elf_path, cfg.boot_path)


    def _on_a2l_failed(self, err: str) -> None:
        self._log_info("A2L addressing FAILED:")
        self._log_info(err)
        QMessageBox.critical(self, "A2L addressing failed", "A2L addressing sırasında hata oluştu. Log'u kontrol et.")
        self._set_status("A2L addressing failed")
        self.run_btn.setEnabled(True)

    def _on_t32_done(self):
        self._log_info("TRACE32 flash OK")

        if self._pending_cfg is None:
            self._log_info("WARN: TRACE32 finished but no pending config found. Skipping VISION.")
            self._set_status("Ready")
            self.run_btn.setEnabled(True)
            return


        cfg = self._pending_cfg
        if not cfg:
            return
        a2l = os.path.normpath(cfg.addressed_a2l_path)
        s19 = os.path.normpath(cfg.s19_path)
        print(a2l)
        print(s19)
        self._create_vision_package(a2l, s19)

    def _on_t32_failed(self, err: str):
        self._log_info("TRACE32 flash FAILED")
        self._log_info(err)
        QMessageBox.critical(self, "TRACE32 Error", "TRACE32 flash failed")
        self.run_btn.setEnabled(True)

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
