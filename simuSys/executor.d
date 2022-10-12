//sourced from https://github.com/dlang/dmd/blob/master/samples/listener.d

import std.string;
import std.range;
import std.file;
import std.process;
import std.algorithm.searching;
import std.algorithm : remove;
import std.conv : to;
import std.socket : InternetAddress, Socket, SocketException, SocketSet, TcpSocket;
import std.stdio : writeln, writefln;
import tinyredis;
import std.parallelism;
import std.concurrency;
import core.atomic;
import core.time : Duration, msecs, hnsecs, nsecs;
import core.thread.threadbase;
import std.net.curl;
import std.json;
import simuSys.classes.workload;
import std.datetime.date : DateTime;
import std.datetime.systime : SysTime, Clock;

shared int[] freedServers;
shared int[] freedContainers;
shared int[] freedPorts;
shared int serverNum = 1;
shared int containerNum = 1;
shared int portNum = 7200;
shared bool cAddGet = false;
shared bool cDelGet = false;
shared bool sAddGet = false;
shared bool sDelGet = false;
shared bool reqGet = false;
Socket[string] socks;

void retryThreadStartUntilSuccess(Redis redis,string[string] cmdVals,Socket[string] socks)
{
    bool noStart = true;
    while(noStart)
    {
        try
        {
            auto t = task!handleInput(redis,cmdVals,socks);
            t.executeInNewThread();
            //t.workForce;
            noStart = false;
        }
        catch (ThreadError e)
        {
            writefln("Error with threading: %s ",e.message());
            writefln("Error with threading Trace: %s ",e.info);
            foreach(item; e.info)
            {
                writefln("%s",item);
            }
        }
    }
}

void waitSignal(shared ref bool sig)
{
    while(!sig)
    {

    }
}

int assignAndIncrementPortNum()
{
    synchronized
    {
        int retPort = portNum;
        atomicOp!"+="(portNum, 1);    
        return retPort;
    }
}

Response execRedis(Redis db,string query)
{
    synchronized
    {
        return db.send(query);
    }
}



void refreshFreedEntities(Redis db)
{
    synchronized 
    {
        writefln("REFRESH\n");
        string freeConQuery = format("SMEMBERS free_containers");
        Response containers = execRedis(db,freeConQuery);
        writefln("freeContainersResult %s",containers);
        foreach(k,v; containers.values)
        {
            if(!canFind(freedContainers,to!int(v.value)))
            {
                freedContainers ~= to!int(v.value);
            }
        }

        string freeServQuery = format("SMEMBERS free_servers");
        Response servers = execRedis(db,freeServQuery);
        //writefln("%s\n",servers);
        foreach(k1,v1; servers.values)
        {
            if(!canFind(freedServers,to!int(v1.value)))
            {
                freedServers ~= to!int(v1.value);
                //writefln("%s\n",v1);
            }
        }

        string freePortQuery = format("SMEMBERS free_Ports");
        Response ports = execRedis(db,freePortQuery);
        foreach(k2,v2; ports.values)
        {
            if(!canFind(freedPorts,to!int(v2.value)))
            {
                freedPorts ~= to!int(v2.value);
            }
        }
    }
    
}

string[string] processInput(string input)
{
    string[string] cmdVals;

    string[] tuples = input.split(",");
    foreach (string tuple; tuples)
    {
        if(tuple != "" && tuple != "\n")
        {
            string[] token = tuple.split(":");
            if(token.length > 1)
            {
                cmdVals[token[0]] = token[1];
            }
            else
            {
                //writefln("odd len 1 array! %s\n",token);
                //writefln("whole input %s\n",input);
            }
        }
    }

    return cmdVals;
}

void spinUpContainer(Socket obsSock,string servName,int servPort,string conName,int containerPort,string conType,int conCPU,int conMEM,string agent)
{
    bool noError = true;
    string cmd1 = format("vboxmanage controlvm \"%s\" natpf1 \"%s,tcp,,%s,,%s\"",servName,conName,containerPort,containerPort);
    auto res1 = executeShell(cmd1);
    if(res1.status != 0)
    {
        noError = false;
        writefln("VM modification failed\n %s\n",cmd1);
        writefln("%s\n",res1);
    }

    string cmd2 = format("ssh -o StrictHostKeyChecking=no 0.0.0.0 -p %s 'docker run --name %s -d -p %s:8000 app%s'",servPort,conName,containerPort,toLower(conType));
    auto res2 = executeShell(cmd2);
    if(res2.status != 0)
    {
        noError = false;
        writefln("Container Creation failed\n %s\n",cmd2);
        writefln("%s\n",res2);
    }

    if(noError)
    {
        writefln("Container successfully spun up!\n");
        string data = format("type:containeradd,conName:%s,conPort:%s,conType:%s,servName:%s,servPort:%s,conCPU:%s,conMEM:%s,agent:%s,buff:buff",
        conName,containerPort,conType,servName,servPort,conCPU,conMEM,agent);
        synchronized 
        {
            obsSock.send(data);
        }
    }
}

void shutDownContainer(Redis db,Socket obsSock,string servName,int servPort,string conName,int conCPU,int conMEM)
{
    bool noError = true;
    
    string cmd2 = format("ssh -o StrictHostKeyChecking=no 0.0.0.0 -p %s 'docker stop %s'", servPort,conName);
    auto res2 = executeShell(cmd2);
    if(res2.status != 0)
    {
        noError = false;
        writefln("Container shutdown failed\n %s\n",cmd2);
         writefln("%s\n",res2);
    }

    string cmd3 = format("ssh -o StrictHostKeyChecking=no 0.0.0.0 -p %s 'docker rm %s'", servPort,conName);
    auto res3 = executeShell(cmd3);
    if(res3.status != 0)
    {
        noError = false;
        writefln("Container deletion failed\n %s\n",cmd3);
         writefln("%s\n",res3);
    }

    string cmd1 = format("VBoxManage controlvm %s natpf1 delete %s",servName,conName);
    auto res1 = executeShell(cmd1);
    if(res1.status != 0)
    {
        noError = false;
        writefln("VM modification failed\n %s\n",cmd1);
         writefln("%s\n",res1);
    }

    if(noError)
    {
        writefln("Container %s successfully shut down!\n",conName);
        string data = format("type:containerdel,conName:%s,servName:%s,conCPU:%s,conMEM:%s,buff:buff",conName,servName,conCPU,conMEM);
        synchronized 
        {
            obsSock.send(data);
        }
    }
}

void spinUpServer(Socket obsSock,string servName,int servPort,int CPU,float MEM,string region)
{
    //writefln("here!!!2\n");
    bool noError = true;
    string cmd1 = format("vboxmanage clonevm serverImage --name=%s --snapshot=serverImageSnap --register --options=Link",servName);
    auto res1 = executeShell(cmd1);
    if(res1.status != 0)
    {
        noError = false;
        writefln("Clone creation failed\n %s\n",cmd1);
    }

    string cmd2 = format("vboxmanage modifyvm \"%s\" --natpf1 \"serverssh,tcp,,%s,,22\"",servName,servPort);
    auto res2 = executeShell(cmd2);
    if(res2.status != 0)
    {
        noError = false;
        writefln("Vm mod failed\n %s\n",cmd2);
    }

    string cmd3 = format("vboxmanage startvm \"%s\" --type headless",servName);
    auto res3 = executeShell(cmd3);
    if(res3.status != 0)
    {
        noError = false;
        writefln("Vm run failed\n %s\n",cmd3);
    }

    if(noError)
    {
        writefln("Server successfully spun up!\n");
        string data = format("type:serveradd,servName:%s,servPort:%s,servCPU:%s,servMem:%s,region:%s,buff:buff",servName,servPort,CPU,MEM,region);
        synchronized 
        {
            obsSock.send(data);
        }
    }
}

void shutDownServer(Redis db,Socket obsSock,string servName)
{
    bool noError = true;
    string cmd1 = format("vboxmanage controlvm %s poweroff soft",servName);
    auto res1 = executeShell(cmd1);
    if(res1.status != 0)
    {
        noError = false;
        writefln("VM shutdown failed!\n %s\n",cmd1);
    }

    string cmd2 = format("VBoxManage unregistervm --delete %s",servName);
    auto res2 = executeShell(cmd2);
    if(res2.status != 0)
    {
        noError = false;
        writefln("VM deletion failed!\n %s\n",cmd2);
    }

    if(noError)
    {
        writefln("Server successfully shut down!\n");
        string data = format("type:serverdel,servName:%s,buff:buff",servName);
        synchronized 
        {
            obsSock.send(data);
        }
    }
}

void totalShutDown(Redis db,Socket obsSock,Socket orchSock)
{
    string[] servers;

    string regionsQuery = format("SMEMBERS regions");
    Response regions = execRedis(db,regionsQuery);
    //writefln("%s",regionsQuery);

    foreach(k,v; regions.values)
    {
        string serverQuery = format("SMEMBERS %s_servers",v.value);
        Response rServs = execRedis(db,serverQuery);
        writefln("%s",serverQuery);

        foreach(k1,v1; rServs.values)
        {
            writefln("%s",v1.value);
            servers ~= v1.value;
        }
    }

    writefln("%s",servers);

    foreach(string serv; servers)
    {
        shutDownServer(db,obsSock, serv);
    }

    synchronized 
    {
        orchSock.send("cmd:shutDownComsExecuted,buff:buff\r\n");
    }

    writefln("All servers shut down!\n");
}

void sendRequest(int port, Mtask t,SysTime timestamp,Socket obsSock,Redis db,string[string] cmdVals)
{
    int cpu = 0;
    float mem = 0;

    if(t.type == "A")
    {
        cpu = 1;
        mem = .5;
    }
    else if(t.type == "B")
    {
        cpu = 1;
        mem = 1;
    }
    else if(t.type == "C")
    {
        cpu = 1;
        mem = 1;
    }
    else 
    {
        cpu = 1;
        mem = 1;
    }
    
    //todo if it has dependencies, wait on dependency, need to check redis.
    if(t.dependency != -1 )
    {
        string wlid = t.id.split("_")[0];

        string checkDepQuery = format("HGETALL %s_%s",wlid,t.dependency);
        auto dep = execRedis(db,checkDepQuery);
        writefln("dep: %s\n",dep);

        while(!empty(dep))
        {
            dep = execRedis(db,checkDepQuery);
        }
    }

    int complete = 0;
    int timeout = 0;
    int rejected = 0;

    //initial entry of task will be edited as time goes on
    string initdata = format("type:reqStatus,tid:%s,tType:%s,region:%s,completed:%s,elapsed:%s,timeout:%s,rejected:%s,server:%s,con:%s,tCPU:%s,tMEM:%s,buff:buff",
    t.id,t.type,t.region,0,0,0,0,cmdVals["server"],cmdVals["con"],cpu,mem);
    synchronized 
    {
        obsSock.send(initdata);
    }

    string url = format("localhost:%s/simu",port);
    auto res = post(url, ["jobmem" : to!string(mem), "jobcpu" : to!string(cpu)]);
    JSONValue resJSON = parseJSON(res);
    SysTime timestamp2 = Clock.currTime();
    Duration dur = timestamp2 - timestamp;
    long elap = dur.total!"msecs";

    writefln("timestamp1 %s \n",timestamp);
    writefln("timestamp2 %s \n",timestamp2);
    writefln("res: %s\n",res);
    while(resJSON["message"].str == "FAIL")
    {
        writefln("waiting on freed resources!: %s\n",res);
        res = post(url, ["jobmem" : to!string(mem), "jobcpu" : to!string(cpu)]);
        SysTime timestamp3 = Clock.currTime();
        dur = timestamp3 - timestamp;
        elap = dur.total!"msecs";

        if(elap > t.timeToComplete * 1000)
        {
            timeout = 1;
        }

        string data = format("type:reqStatus,tid:%s,tType:%s,region:%s,completed:%s,elapsed:%s,timeout:%s,rejected:%s,server:%s,con:%s,tCPU:%s,tMEM:%s,buff:buff",
        t.id,t.type,t.region,complete,elap,timeout,rejected,cmdVals["server"],cmdVals["con"],cpu,mem);
        synchronized 
        {
            obsSock.send(data);
        }

    }
    complete = 1;

    writefln("time elapsed %s\n",elap);
    string data = format("type:reqStatus,tid:%s,tType:%s,region:%s,completed:%s,elapsed:%s,timeout:%s,rejected:%s,server:%s,con:%s,tCPU:%s,tMEM:%s,buff:buff",
    t.id,t.type,t.region,complete,elap,timeout,rejected,cmdVals["server"],cmdVals["con"],cpu,mem);
    
    string result = (timeout == 1) ? "TIMEOUT" : "COMPLETE!";
    
    synchronized 
    {
        string log = format("result:%s,%s\n",result,data);
        append("simuSysLog/executorFinishedTasks.txt", log);
        obsSock.send(data);
    }
}

void handleInput(Redis db,string[string] cmdVals,Socket[string] socks)
{
    writefln("Checkpoint -2 \n");


    /**if(cmdVals["cmd"] == "createVM" || cmdVals["cmd"] == "deleteVM" || cmdVals["cmd"] == "createCon" || cmdVals["cmd"] == "deleteCon")
    {
        synchronized 
        {
            refreshFreedEntities(db);
        }
        
    }*/
    

    if(cmdVals["cmd"] == "createVM")
    {
        writefln("%s\n",freedServers);
        writefln("%s\n",!empty(freedServers));
        //writefln("%s\n",cmdVals);

        string sName = "s";
        int sPort = 0;
        synchronized 
        {
            //refreshFreedEntities(db);
            if(!empty(freedServers))
            {
                writefln("here!!!!\n");
                sName ~= to!string(freedServers[0]);
                freedServers = freedServers.remove(0);
            }
            else 
            {
                sName ~= to!string(serverNum);
                atomicOp!"+="(serverNum,1);
            }

            if(!empty(freedPorts))
            {
                sPort = freedPorts[0];
                freedPorts = freedPorts.remove(0);
            }
            else 
            {
                sPort = assignAndIncrementPortNum();
            }
        }
        //writefln("here!!!1!\n");
        //writefln("%s\n",socks);
        spinUpServer(socks["obs"],sName,sPort,to!int(cmdVals["servCPU"]),to!float(cmdVals["servMEM"]),cmdVals["region"]);
        waitSignal(sAddGet);
        sAddGet = false;
    }
    else if(cmdVals["cmd"] == "deleteVM")
    {
        synchronized
        {
            shutDownServer(db,socks["obs"],cmdVals["servName"]);
            waitSignal(sDelGet);
            sDelGet = false;
        }
    }
    else if(cmdVals["cmd"] == "createCon")
    {
        writefln("Checkpoint -1 \n");
       synchronized 
        {
            /**if(cmdVals["agent"] != "no")
            {
                socks["agent1"].send("cmd:execget2,buff:buff");
                writefln("sending execget2 to agent1!!!!!\n");
            }*/
        
            writefln("Checkpoint 0 \n");
            string cName = "c";
            int cPort = 0;
            int cCPU = 0;
            int cMEM = 0;

            if(cmdVals["conType"] == "A")
            {
                cCPU = 2;
                cMEM = 1;
            }
            else if(cmdVals["conType"] == "B")
            {
                cCPU = 2;
                cMEM = 2;
            }
            else if(cmdVals["conType"] == "C")
            {
                cCPU = 4;
                cMEM = 4;
            }
            else
            {
                cCPU = 8;
                cMEM = 8;
            }
            writefln("Checkpoint 1 \n");
            //refreshFreedEntities(db);
            if(!empty(freedContainers))
            {
                writefln("freedContainers before %s",freedContainers);
                cName ~= to!string(freedContainers[0]);
                freedContainers = freedContainers.remove(0);
                writefln("freedContainers after %s",freedContainers);

                string freeConQuery2 = format("SREM free_containers %s",cName[1..$]);
                writefln("Exec freeconquery : %s\n",freeConQuery2);
                execRedis(db,freeConQuery2);
                refreshFreedEntities(db);
            }
            else 
            {
                cName ~= to!string(containerNum);
                atomicOp!"+="(containerNum, 1);
            }
            writefln("Checkpoint 2 \n");

            if(!empty(freedPorts))
            {
                writefln("freedPorts before %s \n",freedPorts);
                cPort = freedPorts[0];
                freedPorts = freedPorts.remove(0);
                writefln("freedPorts after %s \n",freedPorts);

                string freePortQuery2 = format("SREM free_Ports %s",
                cPort);
                writefln("Exec freePortQuery : %s\n",freePortQuery2);
                execRedis(db,freePortQuery2);
                refreshFreedEntities(db);
            }
            else 
            {
                cPort = assignAndIncrementPortNum();
            }
            writefln("Checkpoint 3 \n");

            string servCPUQuery = format("HMGET %s availableCPU",
            cmdVals["servName"]);
            Response cpuRes = execRedis(db,servCPUQuery);
            foreach(cpuK,cpuV; cpuRes.values)
            {
                if(cCPU > to!int(cpuV))
                {
                    writefln("container creation canceled, not enough CPU! \n");
                    //todo send to agent 3
                    return;
                }
            }
            writefln("Checkpoint 4 \n");

            string servMEMQuery = format("HMGET %s availableMEM",
            cmdVals["servName"]);
            Response memRes = execRedis(db,servMEMQuery);
            foreach(memK,memV; memRes.values)
            {
                if(cMEM > to!int(memV))
                {
                    writefln("container creation canceled, not enough MEM! \n");
                    //todo send to agent 3
                    return;
                }
            }
            writefln("Checkpoint 5 \n");

            string serverPort = "";
            string serverPortQ = format("HMGET %s servPort",
            cmdVals["servName"]);
            Response portRes = execRedis(db,serverPortQ);
            foreach(k,v; portRes.values)
            {
                serverPort = v.value;
            }
            writefln("servportRes %s\n",portRes);
            writefln("servport %s\n",serverPort);
            writefln("Checkpoint 6 \n");

            writefln("Creating container %s!\n",cName);
            spinUpContainer(socks["obs"],cmdVals["servName"],to!int(serverPort),cName,cPort,cmdVals["conType"],cCPU,cMEM,cmdVals["agent"]);
            waitSignal(cAddGet);
            cAddGet = false;
            writefln("Create process for %s done!\n",cName);
        }
    }
    else if(cmdVals["cmd"] == "deleteCon")
    {
        /**synchronized //turn the syncronized into 1 block and make it send execget3, edits will need to be made on python,maybe....try just the one block first
        {
            socks["agent1"].send("cmd:execget2,buff:buff");
        //    writefln("sent to agent1!!!!!\n");
        }*/

        int cCPU = 0;
        int cMEM = 0;

        if(cmdVals["conType"] == "A")
        {
            cCPU = 2;
            cMEM = 1;
        }
        else if(cmdVals["conType"] == "B")
        {
            cCPU = 2;
            cMEM = 2;
        }
        else if(cmdVals["conType"] == "C")
        {
            cCPU = 4;
            cMEM = 4;
        }
        else
        {
            cCPU = 8;
            cMEM = 8;
        }

        synchronized 
        {
            writefln("Deleting %s!\n",cmdVals["conName"]);
            shutDownContainer(db,socks["obs"],cmdVals["servName"],to!int(cmdVals["servPort"]),cmdVals["conName"],cCPU,cMEM);
            waitSignal(cDelGet);
            cDelGet = false;
            writefln("Delete process for %s done!\n",cmdVals["conName"]);
        }
    }
    else if(cmdVals["cmd"] == "totalShut")
    {
        writefln("totalshutdown!\n");
        totalShutDown(db,socks["obs"],socks["orch"]);
    }
    else if(cmdVals["cmd"] == "sendReq")
    {
        writefln("Execturor processign REQ!");
        
        synchronized 
        {
            socks["agent1"].send("cmd:execget,buff:buff");
            writefln("sent to agent1!!!!!\n");
        }

        string servsQ = format("HGETALL s%s",cmdVals["server"]);
        Response servRes = execRedis(db,servsQ);
        if(empty(servRes))
        {
            writefln("server doesn't exist!");
            string data = format("type:reqStatus,tid:%s,tType:%s,region:%s,completed:%s,elapsed:%s,timeout:%s,rejected:%s,server:%s,con:%s,tCPU:%s,tMEM:%s,buff:buff",
            cmdVals["id"],cmdVals["type"],cmdVals["region"],"0","0","0",1,cmdVals["server"],cmdVals["con"],0,0);
            synchronized 
            {
                string log = format("result:SERV_NOT_EXIST,tid:%s,tType:%s,conType:%s,region:%s,completed:%s,elapsed:%s,timeout:%s,rejected:%s,server:%s,con:%s,tCPU:%s,tMEM:%s\n",
                cmdVals["id"],cmdVals["type"],cmdVals["contype"],cmdVals["region"],"0","0","0",1,cmdVals["server"],cmdVals["con"],0,0);
                append("simuSysLog/executorFinishedTasks.txt", log);
                socks["obs"].send(data);
            }
            return;
        }

        string consQ = format("HGETALL c%s",cmdVals["con"]);
        Response conRes = execRedis(db,consQ);
        if(empty(conRes))
        {
            writefln("container doesn't exist!");
            string data = format("type:reqStatus,tid:%s,tType:%s,region:%s,completed:%s,elapsed:%s,timeout:%s,rejected:%s,server:%s,con:%s,tCPU:%s,tMEM:%s,buff:buff",
            cmdVals["id"],cmdVals["type"],cmdVals["region"],"0","0","0",1,cmdVals["server"],cmdVals["con"],0,0);
            synchronized 
            {
                string log = format("result:CON_NOT_EXIST,tid:%s,tType:%s,conType:%s,region:%s,completed:%s,elapsed:%s,timeout:%s,rejected:%s,server:%s,con:%s,tCPU:%s,tMEM:%s\n",
                cmdVals["id"],cmdVals["type"],cmdVals["contype"],cmdVals["region"],"0","0","0",1,cmdVals["server"],cmdVals["con"],0,0);
                append("simuSysLog/executorFinishedTasks.txt", log);
                socks["obs"].send(data);
            }
            return;
        }

        if(cmdVals["type"] != cmdVals["contype"])
        {
            writefln("wrong type!!!\n");
            string data = format("type:reqStatus,tid:%s,tType:%s,region:%s,completed:%s,elapsed:%s,timeout:%s,rejected:%s,server:%s,con:%s,tCPU:%s,tMEM:%s,buff:buff",
            cmdVals["id"],cmdVals["type"],cmdVals["region"],"0","0","0",1,cmdVals["server"],cmdVals["con"],0,0);
            synchronized 
            {
                string log = format("result:WRONG,tid:%s,tType:%s,conType:%s,region:%s,completed:%s,elapsed:%s,timeout:%s,rejected:%s,server:%s,con:%s,tCPU:%s,tMEM:%s\n",
                cmdVals["id"],cmdVals["type"],cmdVals["contype"],cmdVals["region"],"0","0","0",1,cmdVals["server"],cmdVals["con"],0,0);
                append("simuSysLog/executorFinishedTasks.txt", log);
                socks["obs"].send(data);
            }
            return;
        }

        Mtask t = new Mtask(cmdVals["id"],cmdVals["type"],to!float(cmdVals["timetocomplete"]),cmdVals["region"],to!int(cmdVals["deps"]));
        SysTime startTime = Clock.currTime();

        synchronized
        {
            sendRequest(to!int(cmdVals["port"]), t,startTime,socks["obs"],db,cmdVals);
            waitSignal(reqGet);
            reqGet = false;
        }
    }
    else if(cmdVals["cmd"] == "cAddConfirmed")
    {
        writefln("cAddGet set to true\n");
        cAddGet = true;
        //refreshFreedEntities(db);
    }
    else if(cmdVals["cmd"] == "cDelConfirmed")
    {
        writefln("cDelGet set to true\n");
        cDelGet = true;
        //refreshFreedEntities(db);
    }
    else if(cmdVals["cmd"] == "sAddConfirmed")
    {
        writefln("sAddGet set to true\n");
        sAddGet = true;
        //refreshFreedEntities(db);
    }
    else if(cmdVals["cmd"] == "sDelConfirmed")
    {
        writefln("sDelGet set to true\n");
        sDelGet = true;
        //refreshFreedEntities(db);
    }
    else if(cmdVals["cmd"] == "reqConfirmed")
    {
        writefln("reqGet set to true\n");
        reqGet = true;
    }

}

void main(string[] args)
{
    ushort port;

    if (args.length >= 2)
        port = to!ushort(args[1]);
    else
        port = 7000;

    auto listener = new TcpSocket();
    assert(listener.isAlive);
    listener.blocking = false;
    listener.bind(new InternetAddress(port));
    listener.listen(10);
    writefln("Listening on port %d.", port);

    enum MAX_CONNECTIONS = 1200;
    // Room for listener.
    auto socketSet = new SocketSet(MAX_CONNECTIONS + 1);
    Socket[] reads;

    auto redis = new Redis("localhost", 6379);
    while (true)
    {
        socketSet.add(listener);
        long sel;

        foreach (sock; reads)
            socketSet.add(sock);

        Socket.select(socketSet, null, null);

        try
        {
            sel = Socket.select(socketSet, null, null);
        }
        catch (SocketException e)
        {
            socketSet.reset();
            continue;            
        }

        for (size_t i = 0; i < reads.length; i++)
        {
            if (socketSet.isSet(reads[i]))
            {
                char[4096] buf;
                
                long datLength;
                if(sel != -1)
                {
                     datLength = reads[i].receive(buf[]);
                }
                else
                {
                    buf = "cmd:blank,buff:buff";
                    datLength = buf.length;
                }


                if (datLength == Socket.ERROR)
                    writeln("Connection error.");
                else if (datLength != 0)
                {
                    writefln("Received %d bytes from %s: \"%s\"", datLength, reads[i].remoteAddress().toString(), buf[0..datLength]);

                    string[] batches = to!string(buf[0..datLength]).split(",buff:buff");

                    foreach(string cmdLine; batches)
                    {
                        string[string] cmdVals = processInput(cmdLine);
                        writefln("cmdVals: %s\n",cmdVals);

                        if(empty(cmdVals))
                        {
                            writefln("Empty cmdVals instance:\n");
                        }
                        else if(cmdVals["cmd"] == "connect")
                        {
                            socks["obs"] = new TcpSocket(new InternetAddress("127.0.0.1", 7001));
                            //socks["obs"].blocking = false;
                            socks["orch"] = new TcpSocket(new InternetAddress("127.0.0.1", 7002));
                            //socks["orch"].blocking = false;
                            socks["agent1"] = new TcpSocket(new InternetAddress("127.0.0.1", 7003));
                            //socks["agent1"].blocking = false;

                            writefln("ON CONNECT\n");
                            writefln("%s\n",socks);
                            socks["orch"].send("cmd:exFullyConnected,buff:buff");
                        }
                        else if(cmdVals["cmd"] == "blank")
                        {
                            writefln("Skip!\n");
                        }
                        else
                        {
                            try
                            {
                                auto t = task!handleInput(redis,cmdVals,socks);
                                t.executeInNewThread();
                                //t.workForce;
                            }
                            catch (ThreadError e)
                            {
                                writefln("Error with threading: %s ",e.message());
                                writefln("Error with threading Trace: %s ",e.info);
                                foreach(item; e.info)
                                {
                                    writefln("%s",item);
                                }
                                retryThreadStartUntilSuccess(redis,cmdVals,socks);
                            }
                        }

                    }

                    continue;
                }
                else
                {
                    try
                    {
                        // if the connection closed due to an error, remoteAddress() could fail
                        writefln("Connection from %s closed.", reads[i].remoteAddress().toString());
                    }
                    catch (SocketException)
                    {
                        writeln("Connection closed.");
                    }
                }

                // release socket resources now
                reads[i].close();

                reads = reads.remove(i);
                // i will be incremented by the for, we don't want it to be.
                i--;

                writefln("\tTotal connections: %d", reads.length);
            }
        }

        if (socketSet.isSet(listener))        // connection request
        {
            Socket sn = null;
            scope (failure)
            {
                writefln("Error accepting");

                if (sn)
                    sn.close();
            }


            try
            {
                sn = listener.accept();
            }
            catch(SocketException e)
            {
                //writefln("%s\n",e);
                continue;
            }
            //sn = listener.accept();
            
            assert(sn.isAlive);
            assert(listener.isAlive);

            if (reads.length < MAX_CONNECTIONS)
            {
                writefln("Connection from %s established.", sn.remoteAddress().toString());
                reads ~= sn;
                writefln("\tTotal connections: %d", reads.length);
            }
            else
            {
                writefln("Rejected connection from %s; too many connections.", sn.remoteAddress().toString());
                sn.close();
                assert(!sn.isAlive);
                assert(listener.isAlive);
            }
        }

        socketSet.reset();
    }
}