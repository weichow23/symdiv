int rand(void);
void printIntLine(int value);
void printLine(const char *value);
static void fn_002()
{
    int data;
    data = -1;
    if(1)
    {
        data = 0;
    }
    if(0)
    {
        printLine("message");
    }
    else
    {
        if( data != 0 )
        {
            printIntLine(100 / data);
        }
        else
        {
            printLine("message");
        }
    }
}
static void fn_003()
{
    int data;
    data = -1;
    if(1)
    {
        data = 0;
    }
    if(1)
    {
        if( data != 0 )
        {
            printIntLine(100 / data);
        }
        else
        {
            printLine("message");
        }
    }
}
static void fn_004()
{
    int data;
    data = -1;
    if(0)
    {
        printLine("message");
    }
    else
    {
        data = 7;
    }
    if(1)
    {
        printIntLine(100 / data);
    }
}
static void fn_005()
{
    int data;
    data = -1;
    if(1)
    {
        data = 7;
    }
    if(1)
    {
        printIntLine(100 / data);
    }
}
void fn_001()
{
    fn_002();
    fn_003();
    fn_004();
    fn_005();
}
