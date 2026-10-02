int rand(void);
void printIntLine(int value);
void printLine(const char *value);
static void fn_003()
{
    int data;
    data = -1;
    data = 7;
    {
        int dataCopy = data;
        int data = dataCopy;
        printIntLine(100 % data);
    }
}
static void fn_002()
{
    int data;
    data = -1;
    data = 0;
    {
        int dataCopy = data;
        int data = dataCopy;
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
void fn_001()
{
    fn_003();
    fn_002();
}
