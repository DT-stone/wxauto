from wxauto import WeChat
import asyncio


# wx.send_voice_call(who)
# wx.receive_call()
# for i in range(3):
#     wx.SendMsg(f'wxauto测试{i+1}', who)

# # 获取当前聊天页面（文件传输助手）消息，并自动保存聊天图片
# msgs = wx.GetAllMessage(savepic=True)
# for msg in msgs:
#     print(f"{msg[0]}: {msg[1]}")
#
#
# print('wxauto测试完成！')

async def main():
    wx = WeChat()

    """
    todo 当前 chatbox 的 send voice / receive call
    """
    # 发送消息
    who = '三里清风三里路'

    await wx.AddListenChat(who)
    # await wx.receive_call()


if __name__ == '__main__':

    asyncio.run(main())
