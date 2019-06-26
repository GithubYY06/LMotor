# 开发者:       王子饼干
# 时间:         2019年6月6日 12:24:27
# 名称:         小摩托服务器工具组
# 描述:         为小摩托服务器提供主要的开发工具



import threading
import socket
import time
import json
import os

class BaseError(Exception):

    def __init__(self,error_info):

        self.error_info = error_info

    def __str__(self):

        return self.error_info

class MissWorkingFuncError(BaseError):
    '''当你没有设置线程的主函数却希望执行它的时候'''

    def __init__(self):
        super(MissWorkingFuncError,self).__init__("缺少主函数")


class Timer:
    '''计时器类,该计时器只能寄生于一个主循环当中才有效果,其自身不包含线程'''

    def __init__(self,interval=1):
        '''初始化计时器的组件,默认时间间隔为1秒'''

        self.__timer = [time.time(),0]
        self.interval = interval

    def tick(self) -> bool:
        '''该函数放置于主循环中进行判断,如果左值和右值的差距达到interval则输出信号1'''

        self.__timer[1] = time.time()
        if self.__timer[1] - self.__timer[0] >= self.interval:
            self.__timer[0] = self.__timer[1]
            return True
        return False

class _thread_prototype(threading.Thread):
    '''对线程进行简单的封装,使其具有可以终结自己的方式'''

    def __init__(self,func=None,debug=False):
        super(_thread_prototype,self).__init__()
        self.__working = threading.Event()
        self.__working.set()
        self.__wait = threading.Event()
        self.__wait.set()
        # 初始化初始线程的组件,该部分用于控制线程的开始与暂停...

        self.__debug = debug
        self.func = func

    def _initialize(self):
        '''你可以在这里来安装你的主函数'''

        raise NotImplementedError()

    def stop(self):
        '''停止线程'''

        self.__wait.set()
        self.__working.clear()
        if self.__debug:print('thread %s is stoped' % str(self))

    def pause(self):
        '''暂停线程'''

        self.__wait.clear()
        if self.__debug:print('thread %s is paused' % str(self))

    def resume(self):
        '''恢复线程'''

        self.__wait.set()
        if self.__debug:print('thread %s is resumed' % str(self))

    def install(self,func):

        self.func = func

    def run(self):
        '''执行主函数'''

        if not self.func:raise MissWorkingFuncError()
        while self.__working.is_set():
            if self.__wait.is_set():self.func()


class ServerConfigure:
    '''管理服务器的配置文件,该类包含了配置文件的默认位置,该位置不变,如果希望从不同的文件中读取
    配置,可以主动提供一个配置文件位置'''

    cfg_path = "./config/server~config.json"

    def __init__(self,filepath=None,encoding="utf-8"):
        '''初始化所有的配置信息'''

        self.__filepath = filepath if filepath != None else ServerConfigure.cfg_path
        self.__encoding = encoding
        with open(self.__filepath,"r",encoding=encoding) as f:
            self.config = json.load(f)
        
        self.host = self.config["localhost"]                # 主机地址
        self.port = self.config["localport"]                # 主机端口
        self.server_addr = (self.host,self.port)            # 主机地址族
        self.listen = self.config["listen"]                 # 同一时间最多可以监听5个单位
        self.bufsize = self.config["bufsize"]               # 单次发送消息的最大长度
        self.maxconnection = self.config["maxconnection"]   # 同一时间最多支持多少人在线
        self.admin = self.config["admin"]                   # 管理员的帐号和密码
        self.encoding = self.config["encoding"]             # 数据包编码方式
        self.interval = self.config["interval"]
        self.manager_time = self.config["manager_time"]


    def verify_user_login(self,loginform):
        '''验证普通用户提供的帐号和密码是否正确'''

        account,password = loginform
        if account == self.admin["admin_account"] and password == self.admin["admin_password"]:
            return True
        return False

    def update_admin_login_information(self,loginform):
        '''更新管理的帐号和密码'''

        account,password = loginform
        self.config["admin"] = {
            "admin_account":account,
            "admin_password":password
        }
        self.admin = self.config["admin"]
        self.__save_to_local()

    def __save_to_local(self):
        '''把config重写到本地'''

        with open(self.__filepath,"w",encoding=self.__encoding) as f:
            json.dump(self.config,f)

class LogType:

    NORMAL = 0
    WARNING = 1
    ERROR = 2
    UNKNOW = 3

    @staticmethod
    def get_label(t_):

        if t_ == LogType.WARNING:
            return "[WARNING]"
        elif t_ == LogType.NORMAL:
            return "[NORMAL]"
        elif t_ == LogType.ERROR:
            return "[ERROR]"
        else:
            return "[UNKNOW]"

class Logger(_thread_prototype):
    '''提供日志服务'''

    floder = "./log"

    def __init__(self):
        '''初始化日志功能组件'''

        super(Logger,self).__init__()

        self.timer = Timer(60)                  # 时钟，间隔为一秒
        self.date = self.get_date()             # 当前的日期，每过一个小时检查当前日期是否有效
        self.ticks = 0                          # 计时变量
        self.info_list = []                     # 日志消息列表

        self.install(self.working)
        self.index = 0

    def working(self):
        '''维护当前的主类'''

        if self.timer.tick():
            self.save_to_local()
            if len(self.info_list) > 1000:
                self.index += 1
                if self.index >= 30:
                    self.index = 0
                self.info_list.clear()

    def file_number_check(self):
        '''对本地日志文件数量进行检查，如果超过100个日志文件，则清空文件夹'''

        if len(os.listdir(Logger.floder)) >= 100:
            for file in os.listdir(Logger.floder):
                _filepath = "%s/%s" % (Logger.floder,file)
                os.remove(_filepath)
        self.save_to_local()

    def log(self,message,t_:int,position="program"):
        '''记录一条新的日志'''

        log_tuple = (LogType.get_label(t_),self.temp_time(),position,message)
        log = "%s %s at %s:%s" % log_tuple
        self.info_list.append(log)

    def temp_time(self):
        '''当前的具体时间'''

        t = time.localtime()
        time_tuple = (t[0],t[1],t[2],t[3],t[4],t[5])
        return "%d-%d-%d %d:%d:%d" % time_tuple

    def save_to_local(self):
        '''把日志保存到本地文件'''

        _filepath = "%s/%s-%d.log" % (Logger.floder,self.date,self.index)
        with open(_filepath,"w") as f:
            for line in self.info_list:
                f.write(line + "\n")

    def get_date(self):
        '''取得今天的日期'''

        _time_tuple = time.localtime()
        return str(_time_tuple[0]) + "-" + str(_time_tuple[1]) + "-" + str(_time_tuple[2])

    def pass_list(self):

        for msg in self.info_list:
            print(msg)

    def remark(self,info):

        self.info_list.append(info)


log_path = "./log"
if not os.path.exists(log_path):
    os.mkdir(log_path)