import tkinter as tk
import ttkbootstrap as ttkb
from ttkbootstrap.toast import ToastNotification


def show_notification(text):
    toast = ToastNotification(
        title="����������� SBISIIKOconnect",
        message=text,
        duration=5000,
        icon=''
    )

    toast.show_toast()


def add_mouse_moving_trait(window: ttkb.Window | ttkb.Frame | ttkb.Toplevel):
    """�������� ������� ��� ����������� ����"""
    def start_move(window, event=None):
        window.x = event.x
        window.y = event.y
    window.bind("<ButtonPress-1>", start_move)

    def stop_move(window, event=None):
        window.x = None
        window.y = None
    window.bind("<ButtonRelease-1>", stop_move)

    def on_move(window, event=None):
        delta_x = event.x - window.x
        delta_y = event.y - window.y
        x = window.winfo_x() + delta_x
        y = window.winfo_y() + delta_y
        window.geometry(f"+{x}+{y}")
    window.bind("<B1-Motion>", on_move(window))


def add_close_protocol(bool_result: tk.BooleanVar, window: ttkb.Window | ttkb.Frame | ttkb.Toplevel):
    def return_false_closing():
        bool_result.set(False)
        window.destroy()
        return bool_result.get()
    window.protocol("WM_DELETE_WINDOW", return_false_closing)


def set_false_result(bool_result: tk.BooleanVar, window: ttkb.Window | ttkb.Frame | ttkb.Toplevel):
    bool_result.set(False)
    window.destroy()


def set_true_result(bool_result: tk.BooleanVar, window: ttkb.Window | ttkb.Frame | ttkb.Toplevel):
    bool_result.set(True)
    window.destroy()

