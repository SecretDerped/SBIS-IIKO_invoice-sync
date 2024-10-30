import tkinter as tk
import ttkbootstrap as ttkb
from ttkbootstrap.toast import ToastNotification


def show_notification(text):
    toast = ToastNotification(
        title="Уведомление SBISIIKOconnect",
        message=text,
        duration=5000,
        icon=''
    )

    toast.show_toast()


def add_mouse_moving_trait(window):
    """Привязка событий для перемещения окна"""
    def start_move(window_params, event=None):
        window_params.x = event.x
        window_params.y = event.y
    window.bind("<ButtonPress-1>", start_move)

    def stop_move(window_params, event=None):
        window_params.x = None
        window_params.y = None
    window.bind("<ButtonRelease-1>", stop_move)

    def on_move(window_params, event=None):
        if event:
            delta_x = event.x - window_params.x
            delta_y = event.y - window_params.y
            x = window_params.winfo_x() + delta_x
            y = window_params.winfo_y() + delta_y
            window_params.geometry(f"+{x}+{y}")
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

