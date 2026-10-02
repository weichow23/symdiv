int rand(void);
void printIntLine(int value);
void printLine(const char *value);
static const int STATIC_CONST_TRUE = 1;
static const int STATIC_CONST_FALSE = 0;
static void fn_002()
{
    int data;
    data = -1;
    if(STATIC_CONST_TRUE)
    {
        data = 0;
    }
    if(STATIC_CONST_FALSE)
    {
        printLine("message");
    }
    else
    {
        if( data != 0 )
        {
            printIntLine(100 % data);
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
    if(STATIC_CONST_TRUE)
    {
        data = 0;
    }
    if(STATIC_CONST_TRUE)
    {
        if( data != 0 )
        {
            printIntLine(100 % data);
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
    if(STATIC_CONST_FALSE)
    {
        printLine("message");
    }
    else
    {
        data = 7;
    }
    if(STATIC_CONST_TRUE)
    {
        printIntLine(100 % data);
    }
}
static void fn_005()
{
    int data;
    data = -1;
    if(STATIC_CONST_TRUE)
    {
        data = 7;
    }
    if(STATIC_CONST_TRUE)
    {
        printIntLine(100 % data);
    }
}
void fn_001()
{
    fn_002();
    fn_003();
    fn_004();
    fn_005();
}
