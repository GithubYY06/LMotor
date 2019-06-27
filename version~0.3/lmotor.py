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

'''本次的改动，增加了心跳包的机制'''

from lmotor_util import _thread_prototype,ServerConfigure,Timer,Logger,LogType
from _ import encryption,decryption,md5
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

class ServerCommand:

    LOGIN = 0               # 普通客户端登录(晋升为管理员客户端)
    STATUS = 1              # 普通客户端查看服务器状态[目前是否存在管理员,目前有多少台客户端正在连接中]
    LOGOUT = 2              # 管理员登出
    BROADCAST = 3           # 广播一条消息
    VIEW = 4                # 查看现在的服务器状态[所有连接客户端的具体信息]
    CLEAR = 5               # 断开所有的客户端连接
    REBOOT = 6              # 重启服务器
    MSG = 7                 # 给特定的用户发送一条消息
    BREATH = 999            # 心跳包
    # 心跳包只能由服务器发送给客户端

class MsgType:

    RESULT = 0              # 对于请求的结果
    MSG = 1                 # 消息
    LOGIN = 2               # 关于登录的消息
    ERROR = 4               # 无效的命令
    BREATH = 999            # 心跳包


def payback(message_type,**options):
    '''根据消息类型来生成一个字典,字典包含了服务器要传输给客户端的消息
    options:[result]:<0,1>
            [msg]:<string>
            [reason]:<string>
    '''

    _Ret = {"type":message_type}
    if options.get("result"):
        _Ret.setdefault("result",options["result"])
    if options.get("msg"):
        _Ret.setdefault("msg",options["msg"])
    if options.get("reason"):
        _Ret.setdefault("reason",options["reason"])
    if options.get("kwargs"):
        _Ret.setdefault("kwargs",options["kwargs"])
    return str(_Ret)


class LMClient(_thread_prototype):
    '''客户端主类'''

    def __init__(self,pack,server,debug=False):
        '''初始化客户端的所有组件'''

        super(LMClient,self).__init__(debug=debug)
        self.clientsock,self.clientaddr = pack      # 解包
        self.server = server                        # 把服务器设置到可以内部访问,方便客户端线程操作
        self.server.workers.append(self)            # 把自己添加到工作者线程池
        # self.message_queue = []                   # 客户端的消息队列
        self.__debug = debug
        self.valid = True
        self.valid_count = 2

        # self.internal_worker = _thread_prototype(func=self.handle_message)
        # self.internal_worker.start()

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
            self.debug("LMotorClient.send_message:"+str(e))
            self.server.logger.log("unknown error happened when send message to client:%s" % str(e),LogType.ERROR,"LMClient.send_message()")
            self.shutdown()

    def get_sock(self):
        '''获得当前的客户端套接字'''

        return self.clientsock

    def shutdown(self):
        '''关闭客户端线程,这个操作'''

        try:
            self.clientsock.close()             # 关闭与客户端的连接
            self.server.workers.remove(self)    # 从工作者线程池中移除这个对象
            self.stop()                         # 停止这个线程
            self.debug("client %s disconnected from this server" % str(self.clientaddr))
        except Exception as e:
            self.server.logger.log("unknown error happened when send message to client:%s" % str(e),LogType.ERROR,"LMClient.shutdown()")
            pass

    def shutdown_without_remove(self):
        '''关闭客户端线程,但是不从工作者线程移除这个线程'''

        self.clientsock.close()
        self.stop()
        # self.internal_worker.stop()
        self.debug("client %s disconnected from this server" % str(self.clientaddr))

    def working(self):
        '''维护客户端的访问,客户端可以给服务端发送消息,但是只能进行验证和简单的查看服务器消息
        无法做任何高级操作'''

        try:
            _client_message = self.clientsock.recv(LMServer.BUFSIZE)                        # 获取指定大小的报文
            _text = decryption(_client_message)
            if _text:
                _obj = eval(_text.decode(LMServer.ENCODING))        # json对象\
                # print(_obj)
                self.server.handle_user_command(self,_obj)
            else:
                self.send_message(payback(MsgType.ERROR,reason="invalid message"))
        except ConnectionResetError as e:
            self.debug("LMotorClient.working:" + str(e))
            self.shutdown()
        except ConnectionAbortedError as e:
            self.shutdown()
            # 客户端正常被关闭
        except json.JSONDecodeError as e:
            # 如果解析json遇到错误,自动忽略这条消息
            # print("错误2")
            self.send_message(payback(MsgType.ERROR,reason="invalid message"))
        except Exception as e:
            self.shutdown()
            self.server.logger.log("unknown error happened at client main loop:%s" % str(e),LogType.ERROR,"LMClient.working()")

class LMManager(_thread_prototype):
    '''管理员类,服务器的支线类,用于辅助管理员控制服务器'''

    def __init__(self,server,remote_sock,debug=False):
        '''初始化管理员'''

        super(LMManager,self).__init__(self,debug=debug)
        self.server = server
        self.managersock = remote_sock

        self.valid = True
        self.valid_count = 2
        self.time_count = 0
        # self.handler = _thread_prototype(self.handle_message,DEBUG)

        self.__debug = debug
        self.server.managers.append(self)
        self.install(self.working)
        self.start()

    def debug(self,tip):
        '''debug消息'''

        if self.__debug:print(tip)

    def clearsock(self,reason="未设置理由"):
        '''清空管理员线程
        该清空方式包含了停止线程，移除管理员'''

        self.debug("manager is offline")
        self.debug("本次管理员关闭是由于:{}".format(reason))
        self.time_count = 0
        self.managersock.close()
        if self in self.server.managers:
            self.server.managers.remove(self)
        self.stop()

    def send_message(self,info):
        '''给管理员发送一条消息'''

        try:
            self.managersock.send(encryption(info.encode(LMServer.ENCODING)))
        except ConnectionResetError as e:
            self.clearsock(reason="在发送消息的时候遇到了connection_reset_error")
        except Exception as e:
            self.debug("LMotorManager.send_message:" + str(e))
            self.server.logger.log("unknown error happened when send a message to manager:%s" % str(e),LogType.ERROR,"LMMangaer.send_message()")
            self.clearsock(reason="在发送消息的时候遇到了未知的错误:{}".format(str(e)))

    def working(self):
        '''接受管理员的命令并添加到消息队列'''

        if self.valid_count >= 0:
            try:
                _message = self.managersock.recv(LMServer.BUFSIZE)                  # 获取指定大小的报文
                _text = decryption(_message)
                if _text:
                    _obj = eval(_text)
                    # print(_obj)
                    # 管理员线程必须由普通线程晋升而来,不然此处应该设置相应的安全措施
                    self.server.handle_admin_command(self,_obj)
                else:
                    self.send_message(payback(MsgType.ERROR,reason="invalid message"))
            except ConnectionResetError as e:
                self.debug("LMotorManager.working:",e)
                self.clearsock(reason="在接受管理员命令的时候遇到了connection_reset_error")
            except json.JSONDecodeError as e:
                self.send_message(payback(MsgType.ERROR,reason="invalid message"))
            except SyntaxError as e:
                self.debug("LMotorManager.working:" + str(e))
                pass
            except Exception as e:
                self.debug("LMotorManager.working:" + str(e))
                self.clearsock(reason="在接受管理员命令的时候遇到了未知的错误:{}".format(str(e)))
                self.server.logger.log("unknown error happened at manager main loop:%s,%s" % (str(e),str(type(e))),LogType.ERROR,"LMManager.working()")
        else:
            self.clearsock(reason="在接受管理员命令的时候发现管理员已经超过三次没有回复心跳包")

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

        self.managers = []
        # self.manager2 = LMManager(self,debug=DEBUG)
        # 维护管理员进程,管理员进程不会终止,但是在没有管理登录的时候,它不执行自己的代码

        self.reboot_flag = False
        # 重启标签

        self.logger = Logger()
        self.logger.start()
        # 日志记录器

        self.timer = Timer(self.config.interval)
        self.timer_shutdown = Timer(1)
        self.timecounts = 0

        self.install(self.working)

    def breath(self):
        '''心跳包'''

        # self.debug("心跳机制开始运行")
        while 1:
            if self.timer.tick():
                for worker in self.workers:
                    worker.send_message(payback(MsgType.BREATH))
                    if worker.valid:
                        worker.valid = False
                    else:
                        if worker.valid_count < 0:
                            self.debug("由于客户端没有回复心跳包达到上限次数,所以关闭")
                            worker.shutdown()
                        else:
                            worker.valid_count -= 1

                for manager in self.managers:
                    manager.send_message(payback(MsgType.BREATH))
                    if manager.valid:
                        manager.valid = False
                    else:
                        # self.debug('管理员端没有回复')
                        if manager.valid_count < 0:
                            manager.clearsock(reason="管理员超过上限次数没有回复心跳包")
                        else:
                            manager.valid_count -= 1

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
                self.workers[index].send_message(payback(MsgType.MSG,msg=info))

    def broadcast(self,info):
        '''给所有的客户端广播一条消息'''

        for worker in self.workers:
            worker.send_message(payback(MsgType.MSG,msg=info))

    def shutdown_manager(self,target:LMManager):
        '''关闭当前的管理员'''

        target.clearsock(reason="管理员登出或者由于服务器重启")

    def clear_all_managers(self):
        '''清空所有的管理员'''

        for manager in self.managers:
            manager.clearsock(reason="服务器重启,清空所有管理员")


    def debug(self,tip):
        '''输出到控制台的debug信息'''

        if self.__debug:print(tip)

    def handle_admin_command(self,manager,obj):
        '''处理管理员的命令'''

        _type = obj["type"]                         # 先取得管理员的命令类型
        if _type == ServerCommand.BROADCAST:
            # 广播一条消息给所有的客户端

            try:
                self.broadcast(obj["msg"])
                manager.send_message(payback(MsgType.RESULT,msg=SUCCESS))
            except Exception as e:
                manager.send_message(payback(MsgType.RESULT,msg=FAILED,reason=str(e)))
                self.logger.log("error occurred when broadcast message  %s" % str(e),LogType.ERROR,"LMServer.handle_admin_command")

        elif _type == ServerCommand.LOGOUT:
            # 退出当前的管理员

            manager.send_message(payback(MsgType.RESULT,msg=SUCCESS))
            self.shutdown_manager(manager)

        elif _type == ServerCommand.MSG:
            # 给特定的客户端发送一条消息
            
            # self.debug("<debug>:(command 7 is be executed)")
            try:
                _id,_message = obj["id"],obj["msg"]
                _client_host = obj["host"]
                self.sendto(_message,_id,_client_host)
                manager.send_message(payback(MsgType.RESULT,msg=SUCCESS))
            except Exception as e:
                manager.send_message(payback(MsgType.RESULT,msg=FAILED,reason=str(e)))
                self.logger.log("error occurred when send message  %s" % str(e),LogType.ERROR,"LMServer.handle_admin_command")

        elif _type == ServerCommand.CLEAR:
            # 清空所有的客户端

            try:
                self.clearclientsocks()
                manager.send_message(payback(MsgType.RESULT,msg=SUCCESS))
            except Exception as e:
                manager.send_message(payback(MsgType.RESULT,msg=FAILED,reason=str(e)))
                self.logger.log("error occurred when clear service %s" % str(e),LogType.ERROR,"LMServer.handle_admin_command")

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
            manager.send_message(payback(MsgType.RESULT,kwargs={"userlist":_Tmp}))

        elif _type == ServerCommand.REBOOT:
            # 重启服务器,该操作会断开所有的连接

            try:
                self.reboot_flag = True
                self.logger.save_to_local()
                self.clearclientsocks()
                self.clear_all_managers()
                self.server_sock.close()
                manager.send_message(payback(MsgType.RESULT,msg=SUCCESS))
            except Exception as e:
                manager.send_message(payback(MsgType.RESULT,msg=FAILED,reason=str(e)))
                self.logger.log("error occurred when restart server %s" % str(e),LogType.ERROR,"LMServer.handle_admin_command")

        elif _type == ServerCommand.BREATH:

            manager.valid = True
            manager.valid_count = 2
        else:
            # 不匹配任何命令符号
            manager.send_message(payback(MsgType.ERROR,msg=FAILED,reason="Unknown Command"))
        '''心跳包只能由服务器发送给客户端'''

    def handle_user_command(self,client,obj):
        '''处理普通客户端的消息'''

        # print("正在处理客户端的消息",obj)
        if obj["type"] == ServerCommand.LOGIN:
            # 客户端试图登录这个服务器成为管理员，该过程需要得到服务器本地帐号和密码的验证

            acc,pwd = obj["account"],obj["password"]
            if self.config.verify_user_login((acc,pwd)):
                # 确认客户端的信息没有错误之后,准许其成为管理员

                _sock = client.get_sock()
                client.stop();self.workers.remove(client)
                _tmp_manager = LMManager(self,_sock,debug=DEBUG)
                _tmp_manager.send_message(payback(MsgType.LOGIN,msg=SUCCESS))
                # self.managers.append(_tmp_manager)
            else:
                client.send_message(payback(MsgType.LOGIN,msg=FAILED,reason="invalid account or password"))

        elif obj["type"] == ServerCommand.STATUS:
            # 客户端试图取得服务器状态，直接返回
            
            _status_obj = {"clients_number":len(self.workers),"managers_number":len(self.managers)}
            client.send_message(payback(MsgType.RESULT,kwargs=_status_obj))
            # print("普通客户端正在请求服务器状态:返回值确认",str(_status_obj))
        elif obj["type"] == ServerCommand.BREATH:
            # 心跳包

            client.valid = True
            client.valid_count = 2
        else:
            client.send_message(payback(MsgType.ERROR,msg=FAILED,reason="unknown command"))

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
            data = decryption(_message)
            if data:
                data = data.decode(LMServer.ENCODING)
                if data == md5(_random_string,LMServer.ENCODING):
                    self.debug("a connection from %s is built" % str(pack[1]))

                    worker = LMClient(pack,self,debug=True)           # 创建工作者
                    worker.start()
                    worker.send_message(payback(MsgType.RESULT,msg=SUCCESS))
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
heart = _thread_prototype(func=server.breath,debug=DEBUG)
heart.start()
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