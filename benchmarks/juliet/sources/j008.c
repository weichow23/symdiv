int rand(void);
void printIntLine(int value);
void printLine(const char *value);
static void fn_002()
{
    int data;
    data = -1;
    while(1)
    {
        data = 0;
        break;
    }
    while(1)
    {
        if( data != 0 )
        {
            printIntLine(100 % data);
        }
        else
        {
            printLine("message");
        }
        break;
    }
}
static void fn_003()
{
    int data;
    data = -1;
    while(1)
    {
        data = 7;
        break;
    }
    while(1)
    {
        printIntLine(100 % data);
        break;
    }
}
void fn_001()
{
    fn_002();
    fn_003();
}
