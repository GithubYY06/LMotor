'''小摩托服务器
开发时间:2019年6月6日 16:36:49
开发者:王子饼干
版本:0.2
'''

'''
服务器可以处理的命令
普通用户:
    0:升级为管理员(登录)
    1:查看服务器当前的状态,返回当前有多少用户正在连接以及是否已经存在管理员
管理员:
    2:管理员登出
    3:广播一条消息给所有的客户端
    4:查看服务器当前所有客户端的ip和端口
    5:断开所有客户端的连接
    6:重新启动服务器
    7:给特定的客户端发送一条消息
'''

from lmotor_util import _thread_prototype,ServerConfigure,Timer,Logger,LogType
from _ import encryption,decryption
import hashlib
import random
import socket
import json

DEBUG = True
SUCCESS = "success"
FAILED = "failed"

def make_number_sequence(length=6):
    '''生成一个6的随机数字序列'''

    _Ret = ""
    for _ in range(length):_Ret += str(random.randint(0,9))
    return _Ret


def md5(text,encoding):
    '''把text转换为md5加密报文'''

    m2 = hashlib.md5()
    m2.update(text.encode(encoding))
    return m2.hexdigest()

class ServerCommand:

    LOGIN = 0               # 普通客户端登录(晋升为管理员客户端)
    STATUS = 1              # 普通客户端查看服务器状态[目前是否存在管理员,目前有多少台客户端正在连接中]
    LOGOUT = 2              # 管理员登出
    BROADCAST = 3           # 广播一条消息
    VIEW = 4                # 查看现在的服务器状态[所有连接客户端的具体信息]
    CLEAR = 5               # 断开所有的客户端连接
    REBOOT = 6              # 重启服务器
    MSG = 7                 # 给特定的用户发送一条消息

class MsgType:

    RESULT = 0              # 对于请求的结果
    MSG = 1                 # 消息

def payback(message_type,message,reason=""):
    '''根据消息类型来生成一个字典,字典包含了服务器要传输给客户端的消息'''

    _Ret = {"type":message_type,"message":message,"reason":reason}
    return str(_Ret)        


class LMClient(_thread_prototype):
    '''客户端主类'''

    def __init__(self,pack,server,debug=False):
        '''初始化客户端的所有组件'''

        super(LMClient,self).__init__(debug=debug)
        self.clientsock,self.clientaddr = pack      # 解包
        self.server = server                        # 把服务器设置到可以内部访问,方便客户端线程操作
        self.server.workers.append(self)            # 把自己添加到工作者线程池
        self.__debug = debug

        self.install(self.working)                  # 安装线程入口

    def debug(self,tip):
        '''根据是否debug来输出一条消息'''

        if self.__debug:print(tip)

    def send_message(self,info):
        '''发送一条消息,该条消息使用服务器加密规则进行加密和解密'''

        try:
            self.clientsock.send(encryption(info.encode(LMServer.ENCODING)))
        except ConnectionResetError as e:
            self.shutdown()
        except Exception as e:
            self.debug(e)
            self.server.logger.log("unknown error happened when send message to client:%s" % str(e),LogType.ERROR,"LMClient.send_message()")

    def get_sock(self):
        '''获得当前的客户端套接字'''

        return self.clientsock

    def shutdown(self):
        '''关闭客户端线程,这个操作'''

        self.clientsock.close()             # 关闭与客户端的连接
        self.server.workers.remove(self)    # 从工作者线程池中移除这个对象
        self.stop()                         # 停止这个线程
        self.debug("client %s disconnected from this server" % str(self.clientaddr))

    def shutdown_without_remove(self):
        '''关闭客户端线程,但是不从工作者线程移除这个线程'''

        self.clientsock.close()
        self.stop()
        self.debug("client %s disconnected from this server" % str(self.clientaddr))

    def working(self):
        '''维护客户端的访问,客户端可以给服务端发送消息,但是只能进行验证和简单的查看服务器消息
        无法做任何高级操作'''

        try:
            _client_message = self.clientsock.recv(LMServer.BUFSIZE)                        # 获取指定大小的报文
            _obj = json.loads(decryption(_client_message).decode(LMServer.ENCODING))        # json对象
            self.server.handle_user_command(self,_obj)
        except ConnectionResetError as e:
            self.debug(e)
            self.shutdown()
        except ConnectionAbortedError as e:
            pass
            # 客户端正常被关闭
        except Exception as e:
            self.server.logger.log("unknown error happened at client main loop:%s" % str(e),LogType.ERROR,"LMClient.working()")

class LMManager(_thread_prototype):
    '''管理员类,服务器的支线类,用于辅助管理员控制服务器'''

    def __init__(self,server,debug=False):
        '''初始化管理员'''

        super(LMManager,self).__init__(self,debug=debug)
        self.server = server
        self.managersock = None

        self.__debug = debug
        self.install(self.working)

    def online(self):
        '''判断管理员是否在线'''

        return self.managersock != None

    def debug(self,tip):
        '''发送一条debug消息'''

        if self.__debug:print(tip)

    def set_sock(self,remote_sock):
        '''设置一个新的管理员'''

        self.debug("manager is online")
        self.managersock = remote_sock
        self.resume()

    def clearsock(self):
        '''清空管理员线程'''

        self.debug("manager is offline")
        self.managersock.close()
        self.managersock = None
        self.pause()

    def send_message(self,info):
        '''给管理员发送一条消息'''

        try:
            self.managersock.send(encryption(info.encode(LMServer.ENCODING)))
        except ConnectionResetError as e:
            self.clearsock()
        except Exception as e:
            self.debug(e)
            self.server.logger.log("unknown error happened when send a message to manager:%s" % str(e),LogType.ERROR,"LMMangaer.send_message()")

    def working(self):
        '''接受管理员的命令并执行'''

        if self.managersock:
            try:
                _message = self.managersock.recv(LMServer.BUFSIZE)                  # 获取指定大小的报文
                _obj = json.loads(decryption(_message).decode(LMServer.ENCODING))
                # 管理员线程必须由普通线程晋升而来,不然此处应该设置相应的安全措施
                self.server.handle_admin_command(_obj)
            except ConnectionResetError as e:
                self.debug(e)
                self.clearsock()
            except json.JSONDecodeError as e:
                pass
            except Exception as e:
                self.debug(e)
                self.server.logger.log("unknown error happened at manager main loop:%s" % str(e),LogType.ERROR,"LMManager.working()")


class LMServer(_thread_prototype):
    '''服务器主类'''

    BUFSIZE = 0
    MAXCONNECTION = 0
    ENCODING = None

    def __init__(self,debug=False):
        super(LMServer,self).__init__(None,debug)
        self.__debug = debug

        self.config = ServerConfigure()
        LMServer.BUFSIZE = self.config.bufsize
        LMServer.MAXCONNECTION = self.config.maxconnection
        LMServer.ENCODING = self.config.encoding
        # 设置服务器的配置为LMServer的静态变量,方便其他单位访问...

        self.server_sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        # 构建一个TCP流套接字

        self.server_sock.bind(self.config.server_addr)
        self.server_sock.listen(self.config.listen)
        # 开始服务器监听
    
        self.workers = []
        # 维护所有的客户端线程,客户端线程在workers列表中的索引即为客户端的ID号

        self.manager = LMManager(self,debug=True)
        self.manager.start()
        # 维护管理员进程,管理员进程不会终止,但是在没有管理登录的时候,它不执行自己的代码

        self.reboot_flag = False
        # 重启标签

        self.logger = Logger()
        self.logger.start()
        # 日志记录器

        self.install(self.working)

    def clearclientsocks(self):
        '''清空所有的客户端线程'''

        while len(self.workers) > 0:
            now = self.workers.pop()
            now.shutdown_without_remove()
        self.debug("all clients has been removed from workers")
            

    def sendto(self,info,index,client_host):
        '''给指定的客户端发送一条消息'''

        if index in range(len(self.workers)):
            if client_host == self.workers[index].clientaddr[0]:
                self.workers[index].send_message(info)

    def broadcast(self,info):
        '''给所有的客户端广播一条消息'''

        for worker in self.workers:
            worker.send_message(info)

    def shutdown_manager(self):
        '''关闭当前的管理员'''

        self.manager.clearsock()

    def debug(self,tip):
        '''输出到控制台的debug信息'''

        if self.__debug:print(tip)

    def handle_admin_command(self,obj):
        '''处理管理员的命令'''

        _type = obj["type"]                         # 先取得管理员的命令类型
        if _type == ServerCommand.BROADCAST:
            # 广播一条消息给所有的客户端

            self.broadcast(obj["msg"])

        elif _type == ServerCommand.LOGOUT:
            # 退出当前的管理员

            self.shutdown_manager()

        elif _type == ServerCommand.MSG:
            # 给特定的客户端发送一条消息
            
            # self.debug("<debug>:(command 7 is be executed)")
            _id,_message = obj["id"],obj["msg"]
            _client_host = obj["host"]
            self.sendto(_message,_id,_client_host)

        elif _type == ServerCommand.CLEAR:
            # 清空所有的客户端

            self.clearclientsocks()

        elif _type == ServerCommand.VIEW:
            # 返回当前的服务器状态,即当前的所有的客户端
            # self.debug("<debug>:(command 4 is be executed)")
            _Tmp = [];_id = 0
            for worker in self.workers:
                host,port = worker.clientaddr
                _Tmp.append({
                    "id":_id,
                    "host":host,
                    "port":port
                })
                _id += 1
            self.manager.send_message(str(_Tmp))

        elif _type == ServerCommand.REBOOT:
            # 重启服务器,该操作会断开所有的连接

            self.reboot_flag = True
            self.logger.save_to_local()
            self.clearclientsocks()
            self.shutdown_manager()
            self.server_sock.close()


    def handle_user_command(self,client,obj):
        '''处理普通客户端的消息'''

        if obj["type"] == ServerCommand.LOGIN:
            # 客户端试图登录这个服务器成为管理员，该过程需要得到服务器本地帐号和密码的验证

            if not self.manager.online():
                acc,pwd = obj["account"],obj["password"]
                if self.config.verify_user_login((acc,pwd)):
                    # 确认客户端的信息没有错误之后,准许其成为管理员

                    _sock = client.get_sock()
                    client.stop();self.workers.remove(client)
                    self.manager.set_sock(_sock)
                    self.manager.send_message(payback(MsgType.RESULT,SUCCESS))
                else:
                    client.send_message(payback(MsgType.RESULT,FAILED,"invalid account or password"))
            else:
                client.send_message(payback(MsgType.RESULT,FAILED,"manager is already online"))

        elif obj["type"] == ServerCommand.STATUS:
            # 客户端试图取得服务器状态，直接返回

            _status_obj = {"clients_number":len(self.workers),"is_command_online":self.manager.online()}
            client.send_message(str(_status_obj))


    def working(self):
        '''维护服务器的主逻辑代码'''

        try:
            self.debug("wait for connection...")
            pack = self.server_sock.accept()       # 接受客户端的连接
            _clientsock,_addr = pack               # 解包
            # 以下代码用于验证客户端是否是有效的客户端
            _random_string = make_number_sequence()
            _clientsock.send(encryption(_random_string.encode(LMServer.ENCODING)))
            _message = _clientsock.recv(LMServer.BUFSIZE)
            data = decryption(_message).decode(LMServer.ENCODING)
            if data:
                if data == md5(_random_string,LMServer.ENCODING):
                    self.debug("a connection from %s is built" % str(pack[1]))

                    worker = LMClient(pack,self,debug=True)           # 创建工作者
                    worker.start()
                else:
                    _clientsock.close()
            else:
                _clientsock.close()
            # 以上代码用于验证客户端是否是有效的客户端
            # 遇到无效的客户端时直接关闭
        except Exception as e:
            self.logger.log("unknow error happened at server main loop:%s" % str(e),LogType.ERROR,position="LMServer.working()")

server = LMServer(debug=DEBUG)
server.start()
while 1:
    try:
        if server.reboot_flag:
            server.logger.log("server will restart",LogType.NORMAL,"OutMainLoop")
            server.stop()
            server = LMServer(debug=DEBUG)
            server.start()
            server.reboot_flag = False
            server.logger.log("server restart successfully",LogType.NORMAL,"OutMainLoop")
    except Exception as e:
        server.logger.log("unknown error happened when restart:%s" % str(e),LogType.ERROR,"OutMainLoop")