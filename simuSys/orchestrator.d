import std.string;
import std.process;
import std.algorithm : remove;
import std.conv : to;
import std.socket : InternetAddress, Socket, SocketException, SocketSet, TcpSocket;
import std.stdio : writeln, writefln;
import tinyredis;
import std.parallelism;

shared bool exFullyConnected = false;

string[string] processInput(string input)
{
    string[string] cmdVals;

    string[] tuples = input.split(",");
    foreach (string tuple; tuples)
    {
        string[] token = tuple.split(":");
        cmdVals[token[0]] = token[1];
    }

    return cmdVals;
}

void parallelSocketSend(Socket sock,string com)
{
    sock.send(com);
}

void startupServers(ref Socket[string] socks)
{
    string[] initServComs;

    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:NA,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:SA,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:EU,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:AF,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:AS,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:AU,buff:buff");

    foreach(string com; initServComs)
    {
        for(int i = 0; i < 3; i++)
        {
            auto t = task!parallelSocketSend(socks["exec"],com);
            t.executeInNewThread();
            t.yieldForce;
        }
    }

}

void startupCons(ref Socket[string] socks)
{
    for(int i = 1; i <= 18; i++)
    {
        string containerCom1 = format("cmd:createCon,servName:s%s,conType:A,buff:buff",i);
        string containerCom2 = format("cmd:createCon,servName:s%s,conType:B,buff:buff",i);
        string containerCom3 = format("cmd:createCon,servName:s%s,conType:C,buff:buff",i);
        string containerCom4 = format("cmd:createCon,servName:s%s,conType:D,buff:buff",i);

        socks["exec"].send(containerCom1);
        socks["exec"].send(containerCom2);
        socks["exec"].send(containerCom3);
        socks["exec"].send(containerCom4);
    }
}

void initEnvironment(ref Socket[string] socks,ref Pid[] pids,Redis db)
{
    string basePath = "/home/dev/Projects/thesis/SimuApp/simuSys";
    string cmd1 = format("%s/executor",basePath);
    string cmd2 = format("%s/observer",basePath);

    Pid pid1 = spawnProcess(cmd1);
    Pid pid2 = spawnProcess(cmd2);

    pids ~= pid1;
    pids ~= pid2;

    string regionQuery = format("SADD regions NA SA EU AF AS AU");
    db.send(regionQuery);

    bool connect1 = false;
    while(!connect1)
    {
        try
        {
            socks["exec"] = new TcpSocket(new InternetAddress("127.0.0.1", 7000));
            connect1 = true;
        }
        catch(SocketException e)
        {
            connect1 = false;
        }
    }

    bool connect2 = false;
    while(!connect2)
    {
        try
        {
            socks["obs"] = new TcpSocket(new InternetAddress("127.0.0.1", 7001));
            connect2 = true;
        }
        catch(SocketException e)
        {
            connect2 = false;
        }
    }
    
    string execLinkCommand = format("cmd:connect,buff:buff");
    socks["exec"].send(execLinkCommand);

    //wait for socks to be fully connected
    while(!exFullyConnected)
    {

    }

    writefln("Executor and Observer are online! \n");

    startupServers(socks);
    //startupCons(socks);

    writefln("All servers and containers are up! \n");
}

void shutDownEnvironment(ref Socket[string] socks,ref Pid[] pids,Redis db)
{
    string totalShutDownCom = "cmd:totalShut,buff:buff";
    socks["exec"].send(totalShutDownCom);

    string flushQuery = "flushall";
    db.send(flushQuery);

    foreach(Pid p; pids)
    {
        //kill(p);
    }
    writefln("All processes are off!\n",);
}

void handleInput(string[string] cmdVals,ref Pid[] pids,ref Socket[string] socks,Redis db)
{
    if(cmdVals["cmd"] == "initEnv")
    {
        initEnvironment(socks,pids,db);
    }
    else if(cmdVals["cmd"] == "shutDownEnv")
    {
        shutDownEnvironment(socks,pids,db);
    }
    else if(cmdVals["cmd"] == "exFullyConnected")
    {
        exFullyConnected = true;
        writefln("%s\n",exFullyConnected);
    }
}

void main(string[] args)
{
    ushort port;

    if (args.length >= 2)
        port = to!ushort(args[1]);
    else
        port = 7002;

    auto listener = new TcpSocket();
    assert(listener.isAlive);
    listener.blocking = false;
    listener.bind(new InternetAddress(port));
    listener.listen(10);
    writefln("Listening on port %d.", port);

    enum MAX_CONNECTIONS = 60;
    // Room for listener.
    auto socketSet = new SocketSet(MAX_CONNECTIONS + 1);
    Socket[] reads;

    auto redis = new Redis("localhost", 6379);
    Pid[] pids;
    Socket[string] socks;
    while (true)
    {
        socketSet.add(listener);

        foreach (sock; reads)
            socketSet.add(sock);

        Socket.select(socketSet, null, null);

        for (size_t i = 0; i < reads.length; i++)
        {
            if (socketSet.isSet(reads[i]))
            {
                char[1024] buf;
                auto datLength = reads[i].receive(buf[]);

                if (datLength == Socket.ERROR)
                    writeln("Connection error.");
                else if (datLength != 0)
                {
                    writefln("Received %d bytes from %s: \"%s\"", datLength, reads[i].remoteAddress().toString(), buf[0..datLength-1]);
                    string[string] cmdVals = processInput(to!string(buf[0..datLength-1]));
                
                    auto t = task!handleInput(cmdVals,pids,socks,redis);
                    t.executeInNewThread();
                    //t.workForce;
                    
                    continue;
                }

                // release socket resources now
                reads[i].close();

                reads = reads.remove(i);
                // i will be incremented by the for, we don't want it to be.
                i--;
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
            sn = listener.accept();
            assert(sn.isAlive);
            assert(listener.isAlive);

            if (reads.length < MAX_CONNECTIONS)
            {
                writefln("Connection from %s established.", sn.remoteAddress().toString());
                reads ~= sn; //takes in new data
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