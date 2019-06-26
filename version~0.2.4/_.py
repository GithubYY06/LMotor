'''
该脚本为服务器的主要的安全措施,该脚本的控制和上传必须由最高管理员控制
该加密和解密规则必须为服务器和本地共享
'''


from Crypto.Cipher import AES
from Crypto import Random
from binascii import b2a_hex
import hashlib


KEY = b'lmotor_2019_key~'

def md5(text,encoding):
    '''把text转换为md5加密报文'''

    m2 = hashlib.md5()
    m2.update(text.encode(encoding))
    return m2.hexdigest()


def encryption(data,flag=False):
    '''对目标数据进行加密,注意,这里的加密是对二进制的数据进行加密
    如果flag为真,则使用Key作为iv'''

    global KEY
    iv = Random.new().read(AES.block_size)      # 生成一个随机的密钥向量
    if flag:
        iv = KEY
    _aes = AES.new(KEY,AES.MODE_CFB,iv)         # 使用密钥和密钥向量来初始化一个AES对象
    return iv + _aes.encrypt(data)              # 加密后,和密钥向量一起传输


def decryption(data):
    '''对目标数据进行解密,如果遇到错误,则目标数据不规范'''

    try:
        iv = data[:16]                              # 先获取密钥向量
        _aes = AES.new(KEY,AES.MODE_CFB,iv)         # 使用密钥向量和密钥来初始化一个AES对象
        return _aes.decrypt(data[16:])
    except:
        return None

def format_out(data,linecount=10):

    for i in range(len(data)):
        print("{} ".format(hex(data[i])[2:]),end="")
        if (i+1) % linecount == 0:
            print()

if __name__ == '__main__':

    # print(md5("hello world","utf-8"))
    print('\xe5')
