#小摩托工具模块

import threading
import socket
import json
import time

BUFSIZE = 65535

class Timer:
    '''寄生在主循环当中的时钟类'''

    def __init__(self,interval):

        self._timer = [time.time(),0]
        self._interval = interval

    def tick(self):
        '''是否超过时间间隔判断'''

        self._timer[1] = time.time()
        if self._timer[1] - self._timer[0] >= self._interval:
            self._timer[0] = self._timer[1]
            return True
        return False

class COMMAND:
    '''服务器可以接受的所有的命令类型'''

    MSG = 0         # [MSG] object:int,msg:string
    LOGIN = 1       # [LOGIN] account:string,password:string
    LOGOUT = 2      # [LOGOUT]
    BROADCAST = 3   # [BROADCAST] msg:string
    VIEW = 4        # [VIEW]
    CLEAR = 5       # [CLEAR]
    RESTART = 6     # [RESTART]


class _thread_prototype(threading.Thread):
    '''线程原型,该类封装了一个简单的线程原型,提供三个基本函数来控制线程的运行
    该类必须按照规定的模式运行...'''

    def __init__(self):

        super(_thread_prototype,self).__init__()
        self.running = threading.Event()
        self.wait = threading.Event()
        self.running.set()
        self.wait.set()
        # 提供自主控制线程的组件，该组件必须以规定的模式来运行

    def stop(self):
        '''停止线程'''

        self.wait.set()
        self.running.clear()

    def pause(self):
        '''暂停线程'''

        self.wait.clear()

    def resume(self):
        '''恢复线程'''

        self.wait.set()


class LMotorConfig:
    '''保存所有和服务器有关的配置信息'''

    FILEPATH = "./config/server~config.json"

    def __init__(self,filepath=None,encoding="utf-8"):

        self.filepath = LMotorConfig.FILEPATH
        if filepath:
            self.filepath = filepath
        self.encoding = encoding

        with open(self.filepath,"r") as f:
            self._config = json.load(f)

        self._localhost = self._config.get("localhost")
        self._localport = self._config.get("localport")
        self._bufsize = self._config.get("bufsize")
        self._listen_num = self._config.get("listen")

    def _set_localport(self,value:int) -> bool:

        self._config["localport"] = value
        return self._save_data()

    def _verify_login(self,account,password):
        '''验证客户端的帐号和密码是否有效'''

        _obj = self._config["admin"]
        if _obj["admin_account"] == account and _obj["admin_password"] == password:
            return True
        return False
        
    def _save_data(self):
        '''把config中的数据重写到本地'''

        try:
            with open(self.filepath,"w",encoding=self.encoding) as f:
                json.dump(self._config,f)
            return True
        except Exception as e:
            return False

class LMotorWorker(_thread_prototype):
    '''维护单个用户的套接字'''

    def __init__(self,clientsock:socket.socket,_addr:tuple,server,ID:int):

        super(LMotorWorker,self).__init__()
        self._clientsock = clientsock               # 用户套接字
        self._clientaddr = _addr                    # 用户套接字信息
        self._server = server                       # 服务器对象

        self._server._workers.append(self)
        self.id = ID

    def _change_type(self,_type):
        '''更改该用户的类型'''

        self._type = _type

    def sendinfo(self,msg:str):
        '''直接发送消息'''

        try:
            self._clientsock.send(msg.encode())
        except ConnectionResetError as e:
            self.shutdown()
        except Exception as e:
            pass

    def shutdown(self):
        '''停止线程并将其从工作列表中移除'''

        self._clientsock.close()
        self._server._ids.remove(self.id)
        self._server._workers.remove(self)
        self.stop()
        print("用户 %s 已经断开连接了" % str(self._clientaddr))

    def getsock(self):

        return self._clientsock

    def to_obj(self):
        '''把该客户端的信息序列化,预备发送到管理员客户端'''

        return {
            "id":self.id,
            "ip":self._clientaddr[0],
            "port":self._clientaddr[1]
        }

    def run(self):
        '''每隔一段时间发送心跳包来检查客户端是否已经断开了连接'''

        while self.running.is_set():
            if self.wait.is_set():
                try:
                    _client_msg = self._clientsock.recv(BUFSIZE).decode()
                    if self._server._handle_user_command(self,_client_msg):
                        self.stop()
                    # 处理用户的登录事件
                except ConnectionResetError as e:
                    self.shutdown()
                except Exception as e:
                    # print(e)
                    pass


class LMotorManager(_thread_prototype):
    '''管理员'''

    def __init__(self,server):
        super(LMotorManager,self).__init__()

        self._server = server
        self._managersock = None

    def is_online(self):

        return self._managersock != None

    def setsock(self,newsock):
        '''设置新的管理员'''

        self._managersock = newsock

    def sendinfo(self,msg:str):

        self._managersock.send(msg.encode())

    def clearsock(self):
        '''退出'''

        self._managersock.close()
        self._managersock = None
        print("管理员已经离线了...")

    def run(self):
        '''管理员线程'''

        while self.running.is_set():
            if self.wait.is_set():
                if self._managersock:
                    try:
                        _command = self._managersock.recv(BUFSIZE).decode()
                        print(_command)
                        self._server._handle_admin_command(_command)
                    except ConnectionResetError as e:
                        self.clearsock()
                    except Exception as e:
                        print(e)
                        pass


class LMotorServer(_thread_prototype):
    '''定义服务器的主要的运行逻辑'''

    def __init__(self,config:LMotorConfig):
        '''初始化服务器的基本参数'''

        super(LMotorServer,self).__init__()
        self._config = config
        self._serversock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        # 基于ipv4地址的流套接字

        self._localaddr = (config._localhost,config._localport)
        self._serversock.bind(self._localaddr)
        self._serversock.listen(self._config._listen_num)
        # 绑定本地地址到服务器并且开始监听

        self._workers = []
        # 维护所有的客户端套接字

        self._manager = LMotorManager(self)
        self._manager.start()
        self._id = 0
        self._ids = []

    def get_next_id(self):
        '''取得下一个有效的ID号'''

        for _ in range(50):
            if _ not in self._ids:
                return _
        return None

    def stop_server(self):
        '''停止服务器'''

        self.stop()
        self._serversock.close()


    def _handle_admin_command(self,command:str):
        '''该函数定义了如何处理管理员的命令'''

        print("command function is be executed")
        _obj = json.loads(command)      # 序列化
        _type = _obj["type"]            # 取得命令类型

        if _type == COMMAND.MSG:
            # 命令:发送单条信息
            
            _id,_msg = _obj["id"],_obj["msg"]
            self._send_to(_id,_msg)

        elif _type == COMMAND.BROADCAST:
            # 命令:广播信息

            _msg = _obj["msg"]
            self._broadcast(_msg)

        elif _type == COMMAND.LOGOUT:
            # 命令:登出,当管理员客户端登出的时候,这个线程不会回归到
            # 工作者线程列表中

            self._manager.clearsock()

        elif _type == COMMAND.VIEW:
            # 命令:查看所有在线的客户端

            # print("正在处理命令4")
            _ret = str([self._workers[i].to_obj() for i in range(len(self._workers))])
            self._manager.sendinfo(_ret)

        elif _type == COMMAND.CLEAR:
            # 命令:清除所有的客户端连接

            self._clear()

        elif _type == COMMAND.RESTART:
            # 命令:重启服务器

            # print("服务器准备重启")
            self._clear()
            self.stop_server()
            self._manager.clearsock()

    def _clear(self):

        for c in self._workers:
            c.shutdown()

    def _handle_user_command(self,client,command):
        '''处理普通用户命令,普通用户可用的命令只有LOGIN
        普通用户只用于接受消息,不能发送消息'''
        
        _obj = json.loads(command)
        if _obj["type"] == COMMAND.LOGIN:
            return self._login(client,_obj["account"],_obj["password"])
        return False

    def _broadcast(self,msg):
        '''给所有的客户端广播一条消息'''

        for c in self._workers:
            c.sendinfo(msg)

    def _send_to(self,_id:int,msg:str):
        '''遍历所有的客户端,寻找特定的套接字发送信息'''

        for c in self._workers:
            if c.id == _id:
                c.sendinfo(msg)

    def _login(self,client:LMotorWorker,account:str,password:str):
        '''登录到这个服务器,只有正确的管理员帐号和密码才能进行登录'''

        if not self._manager.is_online():
            if self._config._verify_login(account,password):
                self._ids.remove(client.id)
                self._workers.remove(client)
                self._manager.setsock(client.getsock())
                self._manager.sendinfo('{"result":"success"}')
                print("管理员上线了")
                return True
        client.sendinfo('{"result":"failed"}')
        return False

    def run(self):
        '''开始监听客户端的请求'''

        while self.running.is_set():
            if self.wait.is_set():
                if len(self._workers) < 50:
                    try:
                        print("正在监听客户端的请求...")
                        _client,_addr = self._serversock.accept()
                        print("客户端 %s 连接了..." % str(_addr))
                        t = LMotorWorker(_client,_addr,self,self.get_next_id())
                        t.start()
                        self._ids.append(t.id)
                    except OSError as e:
                        pass

if __name__ == '__main__':

    server = LMotorServer(LMotorConfig("./config/server~config.json"))
    server.start()
    while 1:
        if not server.running.is_set():
            print("服务器重启中...")
            server = LMotorServer(LMotorConfig("./config/server~config.json"))
            server.start()