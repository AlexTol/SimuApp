import std.string;
import std.process;
import std.algorithm : remove;
import std.conv : to;
import std.socket : InternetAddress, Socket, SocketException, SocketSet, TcpSocket;
import std.stdio : writeln, writefln;
import tinyredis;
import std.parallelism;

shared bool exFullyConnected = false;
shared bool shutDownComsExecuted = false;
shared Socket exec;
shared Socket obs;

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

void startupServers()
{
    string[] initServComs;
    Socket mExec = cast(Socket)exec;

    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:NA,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:SA,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:EU,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:AF,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:AS,buff:buff");
    initServComs  ~= format("cmd:createVM,servName:s1,servPort:8000,servCPU:8,servMEM:16,region:AU,buff:buff");

    foreach(string com; initServComs)
    {
        for(int i = 0; i < 1; i++)
        {
            auto t = task!parallelSocketSend(mExec,com);
            t.executeInNewThread();
            t.yieldForce;
        }
    }

}

void startupCons()
{
    for(int i = 1; i <= 6; i++)
    {
        string containerCom1 = format("cmd:createCon,servName:s%s,conType:A,buff:buff",i);
        string containerCom2 = format("cmd:createCon,servName:s%s,conType:B,buff:buff",i);
        string containerCom3 = format("cmd:createCon,servName:s%s,conType:C,buff:buff",i);
        string containerCom4 = format("cmd:createCon,servName:s%s,conType:D,buff:buff",i);

        Socket mExec = cast(Socket)exec;

        mExec.send(containerCom1);
        mExec.send(containerCom2);
        mExec.send(containerCom3);
        mExec.send(containerCom4);
    }
}

void initEnvironment(Redis db)
{
    string basePath = "/home/dev/Projects/thesis/SimuApp/simuSys";
    string cmd1 = format("%s/executor",basePath);
    string cmd2 = format("%s/observer",basePath);

    spawnProcess(cmd1);
    spawnProcess(cmd2);

    string regionQuery = format("SADD regions NA SA EU AF AS AU");
    db.send(regionQuery);

    bool connect1 = false;
    while(!connect1)
    {
        try
        {
            exec = cast(shared Socket)(new TcpSocket(new InternetAddress("127.0.0.1", 7000)));
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
            obs = cast(shared Socket)(new TcpSocket(new InternetAddress("127.0.0.1", 7001)));
            connect2 = true;
        }
        catch(SocketException e)
        {
            connect2 = false;
        }
    }
    
    string execLinkCommand = format("cmd:connect,buff:buff");
    Socket mExec = cast(Socket)exec;
    mExec.send(execLinkCommand);

    //wait for socks to be fully connected
    while(!exFullyConnected)
    {

    }

    writefln("Executor and Observer are online! \n");

    startupServers();

    int AUServs = 0;
    while(AUServs < 1)
    {
        auto aus = db.send("SMEMBERS","AU_servers");
        foreach(k,v; aus)
        {
            AUServs += 1;
        }
    }

    writefln("All servers are up! \n");

    startupCons();

    int s6Cons = 0;
    while(s6Cons < 4)
    {
        auto cons = db.send("SMEMBERS","s6_containers");
        foreach(k,v; cons)
        {
            s6Cons += 1;
        }
    }

    writefln("All containers are up! \n");
}

void shutDownEnvironment(Redis db)
{

    string totalShutDownCom = "cmd:totalShut,buff:buff";
    Socket mExec = cast(Socket)exec;
    mExec.send(totalShutDownCom);

    while(!shutDownComsExecuted)
    {

    }

    string flushQuery = "flushall";
    db.send(flushQuery);

    string killEXECcom = "fuser -k 7000/tcp";
    string killOBScom = "fuser -k 7001/tcp";

    //executeShell(killEXECcom);
    //executeShell(killOBScom);

    writefln("All processes are off!\n",);
}

void handleInput(string[string] cmdVals,Redis db)
{
    if(cmdVals["cmd"] == "initEnv")
    {
        initEnvironment(db);
    }
    else if(cmdVals["cmd"] == "shutDownEnv")
    {
        shutDownEnvironment(db);
    }
    else if(cmdVals["cmd"] == "exFullyConnected")
    {
        exFullyConnected = true;
        writefln("%s\n",exFullyConnected);
    }
    else if(cmdVals["cmd"] == "shutDownComsExecuted")
    {
        shutDownComsExecuted = true;
        writefln("%s\n",shutDownComsExecuted);
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
                
                    auto t = task!handleInput(cmdVals,redis);
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

                /**
                if (sn)
                    sn.close();*/
            }
            try
            {
                sn = listener.accept();
            }
            catch(SocketException e)
            {
                writefln("%s\n",e);
                continue;
            }

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