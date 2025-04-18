# -*- coding:utf-8 -*-


from pywinauto import Application

# 启动某个应用程序或连接到已存在的应用程序
app = Application().start('notepad.exe')


def monitor_window():
    try:
        # 你可以使用 wait 方法来等待特定控件出现
        notepad_window = app.window(title="无标题 - 记事本")

        # 等待窗口中某个按钮出现，最多等待10秒
        notepad_window.child_window(control_type="Button", class_name="Button").wait("visible", timeout=10)

        print("按钮出现了，开始操作！")
        notepad_window.child_window(control_type="Button", class_name="Button").click_input()  # 点击按钮
    except Exception as e:
        print("没有找到目标元素或操作失败:", e)


if __name__ == "__main__":
    monitor_window()
