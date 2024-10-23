import ttkbootstrap as ttkb
import tkinter as tk

from tkinter import font
from logging import warning, info

from ttkbootstrap import PRIMARY, OUTLINE, SUCCESS, DANGER

from gui.windows import show_notification, add_mouse_moving_trait, add_close_protocol, set_false_result, set_true_result
from utils.tools import error_windows_size


def get_answer_from_user(text, true_button_text, false_button_text):
    """���������� ���� � �������� �������. ����� ������, ������������ True � False"""
    error_window = ttkb.Toplevel()
    result = tk.BooleanVar()

    # �������� ������ ��� ������
    inner_frame = ttkb.Frame(error_window, borderwidth=0, relief="solid")
    inner_frame.pack(expand=True, fill='both', padx=1, pady=1)

    # ������������� Text ������� ��� ����������� ������ � ����� �����
    error_text = tk.Text(inner_frame, height=16, width=46, wrap='word', fg="red",
                         font=font.nametofont("TkDefaultFont"),
                         relief=tk.FLAT, bd=0)
    error_text.insert('1.0', text)
    error_text.tag_configure("center", justify='center')
    error_text.tag_add("center", "1.0", "end")
    error_text.config(state=tk.DISABLED)
    error_text.pack(pady=0)

    # ���������� ������ ��� �������� ����
    close_button = ttkb.Button(inner_frame, text="X",
                               command=set_false_result(result, error_window),
                               bootstyle=(PRIMARY, OUTLINE))
    close_button.pack(side='top', anchor='ne', padx=5, pady=5)

    # �������� ������ ��� ������
    button_frame = ttkb.Frame(inner_frame)
    button_frame.pack(pady=10)

    repeat_button = ttkb.Button(button_frame, text=false_button_text,
                                command=set_false_result(result, error_window),
                                bootstyle=(SUCCESS, OUTLINE))
    repeat_button.pack(side=tk.LEFT, padx=10)

    continue_button = ttkb.Button(button_frame, text=true_button_text,
                                  command=set_true_result(result, error_window),
                                  bootstyle=(DANGER, OUTLINE))
    continue_button.pack(side=tk.LEFT, padx=10)

    show_notification(text)

    error_window.title("������")
    error_window.overrideredirect(True)  # ������� ����� ����, ������� ������� ������ �����
    error_window.geometry(error_windows_size)
    error_window.config(bg='black')

    def lift_above_all(window, event=None):
        window.lift()
        window.after(100, lift_above_all, ())  # �������� �������� ������ 100 ��

    lift_above_all(error_window)  # ������� lift_above_all ����� ����� �������� ����

    add_close_protocol(result, error_window)
    add_mouse_moving_trait(error_window)
    error_window.wait_variable(result)

    warning(f'����������� �� ������: {text}')
    info(f'������ ������ � �����������: {result.get()}')
    return result.get()
