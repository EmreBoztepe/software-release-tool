# -*- coding: utf-8 -*-
"""
TRACE32 launcher + connector
- Proje içindeki config.t32 ile TRACE32'yi başlatır (-c).
- config.t32'yi parse edip TCP/UDP + PORT/PACKLEN ayarlarını otomatik uygular.
- t32api64.dll (legacy) ile bağlanır ve Program/Message Area'ya mesaj basar.

Kullanım:
  1) Aşağıdaki 3 yolu kendi makinene göre ayarla:
     T32_EXE, DLL_DIR, PROJECT_DIR
  2) Proje klasöründe config.t32 hazır olsun (örnek içerikler aşağıda).
  3) py -3 t32_launcher.py
"""

import os
import time
import ctypes
import subprocess
import sys
from pathlib import Path

# --- KULLANICI AYARLARI (tek sefer) ------------------------------------------
# PowerPC için t32mppc.exe, ARM için t32marm.exe kullanın.
TRACE32_INSTALL = r"D:\T32"  # T32 kurulum kökü (ör: D:\T32)
T32_EXE         = os.path.join(TRACE32_INSTALL, "bin", "windows", "t32mppc.exe")
# t32marm.exe kullanacaksanız üst satırı buna çevirin:
# T32_EXE = os.path.join(TRACE32_INSTALL, "bin", "windows64", "t32marm.exe")

# Legacy API DLL (t32api64.dll) klasörü
DLL_DIR = os.path.join(TRACE32_INSTALL, "demo", "api", "python", "legacy")

# Proje klasörü: config.t32 burada
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.t32")
# (opsiyonel) başlangıç scripti istiyorsanız buraya koyun:
STARTUP_CMM = os.path.join(PROJECT_DIR, "startup.cmm")  # yoksa otomatik atlanır

# TRACE32 açıldıktan sonra kaç sn beklensin (GUI/port hazır için)
BOOT_SLEEP_SEC = 5.0
API_TIMEOUT_SEC = 20.0
# ----------------------------------------------------------------------------


def read_config(path):
    """
    Basit config.t32 parser:
    - RCL=NETTCP veya RCL=NETASSIST
    - PORT=xxxxx
    - PACKLEN=xxxx (sadece UDP'de)
    """
    rcl = None
    port = None
    packlen = None

    if not os.path.isfile(path):
        raise FileNotFoundError(f"config.t32 bulunamadı: {path}")

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue
            u = line.upper().replace(" ", "")
            if u.startswith("RCL="):
                if "NETTCP" in u:
                    rcl = "TCP"
                elif "NETASSIST" in u:
                    rcl = "UDP"
            elif u.startswith("PORT="):
                try:
                    port = str(int(u.split("=", 1)[1]))
                except Exception:
                    pass
            elif u.startswith("PACKLEN="):
                try:
                    packlen = str(int(u.split("=", 1)[1]))
                except Exception:
                    pass

    if rcl is None:
        # Varsayılanı TCP kabul et; istersen değiştir
        rcl = "TCP"
    if port is None:
        port = "20000"
    # UDP ise packlen zorunlu; yoksa 1024'e düş
    if rcl == "UDP" and not packlen:
        packlen = "1024"

    return rcl, port, packlen


def start_trace32_with_config(t32_exe, cfg_path, workdir):
    exe_name = os.path.basename(t32_exe).lower()
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}"],
            universal_newlines=True
        )
        if exe_name in out.lower():
            print("TRACE32 already running.")
            return None
    except Exception:
        pass
        
    cmd = [t32_exe, "-c", cfg_path, "-w", workdir]

    print("TRACE32 başlatılıyor:", " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=workdir)
    return proc


def connect_via_legacy_api(rcl_mode, port, packlen, timeout_s=API_TIMEOUT_SEC):
    """
    Legacy t32api64.dll ile bağlan.
    TCP ise PACKLEN gönderme, UDP ise PACKLEN zorunlu.
    """
    os.add_dll_directory(DLL_DIR)
    dll_path = os.path.join(DLL_DIR, "t32api64.dll")
    # WinDLL -> stdcall
    t32api = ctypes.WinDLL(dll_path)

    # Temiz başlangıç (güvenlik)
    try:
        t32api.T32_Exit()
    except Exception:
        pass

    t32api.T32_Config(b"NODE=", b"localhost")
    t32api.T32_Config(b"PORT=", port.encode("ascii"))

    if rcl_mode == "UDP":
        t32api.T32_Config(b"PACKLEN=", (packlen or "1024").encode("ascii"))
    # TCP'de PACKLEN gönderME

    start = time.time()
    while True:
        rc = t32api.T32_Init()
        if rc == 0 and t32api.T32_Attach(1) == 0 and t32api.T32_Ping() == 0:
            print(f"TRACE32 API bağlantısı OK ({rcl_mode}:{port})")
            return t32api

        if time.time() - start > timeout_s:
            raise RuntimeError(f"API bağlantı zaman aşımı (mode={rcl_mode}, port={port}). "
                               f"T32_Init rc={rc}")
        time.sleep(0.5)


def run_flash(elf_path: str, boot_path: str):
 # 1) config.t32'yi oku
    rcl_mode, port, packlen = read_config(CONFIG_PATH)
    print(f"config.t32 -> RCL={rcl_mode} PORT={port}"
          + (f" PACKLEN={packlen}" if rcl_mode == "UDP" else ""))

    # 2) TRACE32'yi proje config'iyle başlat
    start_trace32_with_config(T32_EXE, CONFIG_PATH, PROJECT_DIR)

    # 3) GUI/port hazır için kısa bekleme
    time.sleep(BOOT_SLEEP_SEC)

    # 4) Legacy API ile bağlan
    t32 = connect_via_legacy_api(rcl_mode, port, packlen)

    # 5) Program/Message Area'ya yaz
    msg = 'PRINT "Python connected via project config.t32"'
    rc = t32.T32_Cmd(msg.encode("utf-8"))
    if rc < 0:
        raise RuntimeError("T32_Cmd hata: Remote API iletişim sorunu")

    elf_path = os.path.abspath(elf_path)
    boot_path = os.path.abspath(boot_path)

    t32.T32_Cmd(f'&ELF="{elf_path}"'.encode("utf-8"))
    t32.T32_Cmd(f'&BOOT="{boot_path}"'.encode("utf-8"))
    t32.T32_Cmd(f'DO "{STARTUP_CMM}"'.encode("utf-8"))

    rc = 5
    if rc < 0:
        raise RuntimeError("T32_Cmd comm error while starting CMM")

    
    state = ctypes.c_int(-1)
    timeout_s = 600.0
    t0 = time.time()

    while True:
        rc = t32.T32_GetPracticeState(ctypes.byref(state))
        if rc != 0:
            raise RuntimeError(f"T32_GetPracticeState failed rc={rc}")

        # 0 genelde NOT_RUNNING (script bitti)
        if state.value == 0:
            break

        if time.time() - t0 > timeout_s:
            raise TimeoutError("CMM timeout: script bitmedi")

        time.sleep(0.1)


    # 6) cmm dogru bitti mi kontrol ##
    msg = ctypes.create_string_buffer(1024)
    status = ctypes.c_uint16(0)

    if t32.T32_GetMessage(ctypes.byref(msg), ctypes.byref(status)) == 0:
        text = msg.value.decode("utf-8", errors="ignore").lower()

        if (status.value & 0x0002) or (status.value & 0x0010):
            raise RuntimeError(f"TRACE32 error (status=0x{status.value:04X}): {text}")

        if "not found" in text or "error" in text:
            raise RuntimeError(f"TRACE32 error message: {text}")

    time.sleep(0.5)
    rc = t32.T32_Cmd(b"go")
    if rc < 0:
        raise RuntimeError("Go command failed")
    
    # 7) Kapat veya açık bırak (örnek kapatıyor)
    time.sleep(20)
    t32.T32_Exit()
    print("Mesaj gönderildi ve bağlantı temiz kapatıldı.")

