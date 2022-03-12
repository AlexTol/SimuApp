//sourced from https://github.com/dlang/dmd/blob/master/samples/listener.d

import std.string;
import std.process;
import std.algorithm : remove;
import std.conv : to;
import std.socket : InternetAddress, Socket, SocketException, SocketSet, TcpSocket;
import std.stdio : writeln, writefln;

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

void spinUpContainer(string servName,int servPort,string conName,int containerPort,string conType)
{
    bool noError = true;
    string cmd1 = format("vboxmanage controlvm \"%s\" natpf1 \"%s,tcp,,%s,,%s\"",servName,conName,containerPort,containerPort);
    auto res1 = executeShell(cmd1);
    if(res1.status != 0)
    {
        noError = false;
        writefln("VM modification failed\n %s\n",cmd1);
    }

    string cmd2 = format("ssh -o StrictHostKeyChecking=no 0.0.0.0 -p %s 'docker run --name %s -d -p %s:8000 app%s'",servPort,conName,containerPort,toLower(conType));
    auto res2 = executeShell(cmd2);
    if(res2.status != 0)
    {
        noError = false;
        writefln("Container Creation failed\n %s\n",cmd2);
    }

    if(noError)
    {
        writefln("Container successfully spun up!\n");
    }
}

void shutDownContainer(string servName,int servPort,string conName)
{
    bool noError = true;
    string cmd2 = format("ssh -o StrictHostKeyChecking=no 0.0.0.0 -p %s 'docker stop %s'", servPort,conName);
    auto res2 = executeShell(cmd2);
    if(res2.status != 0)
    {
        noError = false;
        writefln("Container shutdown failed\n %s\n",cmd2);
    }

    string cmd1 = format("VBoxManage controlvm %s natpf1 delete %s",servName,conName);
    auto res1 = executeShell(cmd1);
    if(res1.status != 0)
    {
        noError = false;
        writefln("VM modification failed\n %s\n",cmd1);
    }

    if(noError)
    {
        writefln("Container successfully shut down!\n");
    }
}

void spinUpServer(string servName,int servPort)
{
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
    }
}

void shutDownServer(string servName)
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
    }
}

void handleInput(string input)
{
    string[string] cmdVals = processInput(input);

    if(cmdVals["cmd"] == "createVM")
    {
        spinUpServer(cmdVals["servName"],to!int(cmdVals["servPort"]));
    }
    else if(cmdVals["cmd"] == "deleteVM")
    {
        shutDownServer(cmdVals["servName"]);
    }
    else if(cmdVals["cmd"] == "createCon")
    {
        spinUpContainer(cmdVals["servName"],to!int(cmdVals["servPort"]),cmdVals["conName"],to!int(cmdVals["conPort"]),cmdVals["conType"]);
    }
    else if(cmdVals["cmd"] == "deleteCon")
    {
        shutDownContainer(cmdVals["servName"],to!int(cmdVals["servPort"]),cmdVals["conName"]);
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

    enum MAX_CONNECTIONS = 1000;
    // Room for listener.
    auto socketSet = new SocketSet(MAX_CONNECTIONS + 1);
    Socket[] reads;

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
                char[4096] buf;
                auto datLength = reads[i].receive(buf[]);

                if (datLength == Socket.ERROR)
                    writeln("Connection error.");
                else if (datLength != 0)
                {
                    writefln("Received %d bytes from %s: \"%s\"", datLength, reads[i].remoteAddress().toString(), buf[0..datLength-1]);
                    handleInput(to!string(buf[0..datLength-1]));
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
            sn = listener.accept();
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