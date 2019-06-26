from _ import encryption,decryption,md5
import socket
import threading
import json

ENCODING = "utf-8"
BUFSIZE = 65535

class LocalMechine:

    def __init__(self,host="10.54.85.212",port=45535):

        self.host = host
        self.port = port
        self.server_addr = (host,port)
        self.localsock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        # self.lock = threading.Lock()
        self.flag = True


    def connect(self):

        try:
            self.localsock.connect(self.server_addr)
            pwd = decryption(self.localsock.recv(BUFSIZE)).decode(ENCODING)
            pwd = encryption(md5(pwd,ENCODING).encode(ENCODING))
            self.localsock.send(pwd)
            return True
        except Exception as e:
            print(e)
            return False

    def show_message(self,msg,flag=False):

        if flag:
            return input(msg)
        else:
            print(msg)


    def working2(self):
        ''' send message to server '''

        while 1:
            if self.flag:
                self.flag = False
                msg = input("client@server")
                self.localsock.send(encryption(msg.encode(ENCODING)))
                print("消息已经发送了")

    def working(self):
        ''' show message from server '''

        while 1:
            try:
                msg = self.localsock.recv(BUFSIZE)
                msg = decryption(msg).decode(ENCODING)
                _obj = eval(msg)
                if _obj.get("type") == 999:
                    msg = str({"type":999})
                    self.localsock.send(encryption(msg.encode(ENCODING)))
                else:
                    print(_obj)
                self.flag = True
            except Exception as e:
                self.show_message(e)
                break

x = LocalMechine()
if x.connect():
    print("已经成功连接到服务器...")
    t1 = threading.Thread(target=x.working,args=())
    t1.start()
    t2 = threading.Thread(target=x.working2,args=())
    t2.start()
else:
    print("连接失败...")
