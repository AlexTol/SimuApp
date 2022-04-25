import socket
import threading
import time
import redis
import random

r = redis.Redis(
    host='localhost',
    port=6379)

def randomServConSelect():
    servs = []
    regions = redis.smembers("regions")
    for r in regions:
        rServs = redis.smembers("{r}_servers")
        for s in rServs:
            servs.append(s)

    ser = random.choice(servs)
    containers = redis.smembers("{ser}_containers")
    return random.choice(containers)
    

#todo sent commands to executor,
def processInput(dat):
    cmdVals = {}
    tuples = dat.split(",")
    for tup in tuples:
        print("%s\n",tup)
        if tup != "" and tup != "\n":
            token = tup.split(":")
            cmdVals[token[0]] = token[1]
    return cmdVals

def agentTime():
    while True:
        time.sleep(1)
        print("do stuff\n")


def handleInput(dat):
    cmdVals = processInput(dat)
    if  cmdVals['cmd'] == "stask":
        #get any tasks rejected
        c = randomServConSelect()
        conInfo = redis.hgetall("{c}")
        conPort = conInfo['conPort']
        conType = conInfo['conType']
        
        execSock.sendall("cmd:sendReq,port:{conPort},type:{conType},buff:buff")
    #print("%s\n",cmdVals)
    


HOST = "127.0.0.1"  # Standard loopback interface address (localhost)
PORT = 7003  # Port to listen on (non-privileged ports are > 1023)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen()

    orchSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    orchSock.connect(('localhost', 7002))
    obsSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    obsSock.connect(('localhost', 7001))
    execSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    execSock.connect(('localhost', 7000))

    orchSock.sendall(b'cmd:agent1FullyConnected,buff:buff')

    t1 = threading.Thread(target=agentTime,args=())
    t1.start()

    conn, addr = s.accept()
    with conn:
        print(f"Connected by {addr}")
        while True:
            data = conn.recv(4096)
            if not data:
                break
            else:
                strDat = data.decode("utf-8")
                print("%s\n",strDat)
                batches = strDat.split(",buff:buff")
                for batch in batches:
                    tRep = threading.Thread(target=handleInput,args=(batch))
                    tRep.start()
                    #handleInput(batch)
                orchSock.sendall(b'cmd:agent1Get,buff:buff')
            #conn.sendall(data)