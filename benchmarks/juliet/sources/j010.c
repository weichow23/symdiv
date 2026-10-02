int rand(void);
void printIntLine(int value);
void printLine(const char *value);
static void fn_003()
{
    int data;
    data = -1;
    data = 7;
    printIntLine(100 / data);
}
static void fn_002()
{
    int data;
    data = -1;
    data = ((int)(rand() & 1 ? (((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) : -(((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) - 1));
    if( data != 0 )
    {
        printIntLine(100 / data);
    }
    else
    {
        printLine("message");
    }
}
void fn_001()
{
    fn_003();
    fn_002();
}
