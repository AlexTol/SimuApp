import std.string;
import std.process;
import std.algorithm : remove;
import std.conv : to;
import std.socket : InternetAddress, Socket, SocketException, SocketSet, TcpSocket;
import std.stdio : writeln, writefln;
import tinyredis;

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

void handleInput(string[string] cmdVals,Redis db)
{

    if(cmdVals["type"] == "serveradd")
    {
        string query = format("HMSET %s servPort \"%s\" servCPU \"%s\" servMEM \"%s\" region \"%s\"",
            cmdVals["servName"],cmdVals["servPort"],cmdVals["servCPU"],cmdVals["servMem"],cmdVals["region"]);
        
        db.send(query);

        writefln("server %s saved!\n",cmdVals["servName"]);
    }
    else if(cmdVals["type"] == "serverdel")
    {
        string conQuery = format("SMEMBERS %s_containers",
        cmdVals["servName"]);
        Response containers = db.send(conQuery);

        foreach(k,v; containers.values)
        {
            string sdelConQuery = format("SREM %s_containers %s",
            cmdVals["servName"],v.value);

            string delConQuery = format("DEL %s",
            v.value);

            db.send(sdelConQuery);
            db.send(delConQuery);
        }

        string query = format("DEL %s",
            cmdVals["servName"]);
        
        db.send(query);

        writefln("server %s deleted!\n",cmdVals["servName"]);
    }
    else if(cmdVals["type"] == "containeradd")
    {
        string query = format("HMSET %s conPort \"%s\" conType \"%s\" servName \"%s\" servPort \"%s\"",
            cmdVals["conName"],cmdVals["conPort"],cmdVals["conType"],cmdVals["servName"],cmdVals["servPort"]);
        
        db.send(query);

        string serverConQuery= format("SADD %s_containers %s",
        cmdVals["servName"],cmdVals["conName"]);
        db.send(serverConQuery);

        writefln("scontainer %s saved!\n",cmdVals["conName"]);
    }
    else if(cmdVals["type"] == "containerdel")
    {
        string setDelQuery = format("SREM %s_containers %s",
        cmdVals["servName"],cmdVals["conName"]);
        db.send(setDelQuery);

        string query = format("Del %s",
            cmdVals["conName"]);
        
        db.send(query);

        writefln("scontainer %s deleted!\n",cmdVals["conName"]);
    }
}

void main(string[] args)
{
    ushort port;

    if (args.length >= 2)
        port = to!ushort(args[1]);
    else
        port = 7001;

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
                    handleInput(cmdVals,redis);
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