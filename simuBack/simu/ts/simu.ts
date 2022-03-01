function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

export async function simulate(type : string)
{
    if(type == "A")
    {
        await sleep(1000);
    }
    else if(type == "B")
    {
        await sleep(2000);
    }
    else if(type == "C")
    {
        await sleep(4000);
    }
    else if(type == "D")
    {
        await sleep(8000);
    }
}