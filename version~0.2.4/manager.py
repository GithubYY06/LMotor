# coding:utf8

import socket
import threading
import hashlib

from Crypto.Cipher import AES
from Crypto import Random
from binascii import b2a_hex

import json

KEY = b'lmotor_2019_key~'


def encryption(data):
    '''对目标数据进行加密,注意,这里的加密是对二进制的数据进行加密'''

    iv = Random.new().read(AES.block_size)      # 生成一个随机的密钥向量
    _aes = AES.new(KEY,AES.MODE_CFB,iv)         # 使用密钥和密钥向量来初始化一个AES对象
    return iv + _aes.encrypt(data)              # 加密后,和密钥向量一起传输


def decryption(data):
    '''对目标数据进行解密,如果遇到错误,则目标数据不规范'''

    try:
        iv = data[:16]                              # 先获取密钥向量
        _aes = AES.new(KEY,AES.MODE_CFB,iv)         # 使用密钥向量和密钥来初始化一个AES对象
        return _aes.decrypt(data[16:])
    except Exception as e:
        print(e)
        return None

def md5(text,encoding):
    '''把text转换为md5加密报文'''

    m2 = hashlib.md5()
    m2.update(text.encode(encoding))
    return m2.hexdigest()

target_host = '10.54.85.212'
target_port = 45535

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((target_host, target_port))
test_string = decryption(client.recv(65535)).decode("utf-8")
client.send(encryption(md5(test_string,"utf-8").encode("utf-8")))

flag = False

def show_server_info(client):

    while 1:
        msg = decryption(client.recv(65535)).decode("utf-8")
        _obj = eval(msg)
        if _obj.get("type") == 999:
            msg = str({"type":999})
            client.send(encryption(msg.encode("utf-8")))
        else:
            print(_obj)

t = threading.Thread(target=show_server_info,args=(client,))
t.start()

while 1:
    if not flag:
        msg = input(">")
        client.send(encryption(msg.encode("utf-8")))
    else:
        break

x = input("程序已经结束...")

    
