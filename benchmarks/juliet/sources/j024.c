int rand(void);
void printIntLine(int value);
void printLine(const char *value);
static const int STATIC_CONST_FIVE = 5;
static void fn_002()
{
    int data;
    data = -1;
    if(STATIC_CONST_FIVE==5)
    {
        data = ((int)(rand() & 1 ? (((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) : -(((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) - 1));
    }
    if(STATIC_CONST_FIVE!=5)
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
    if(STATIC_CONST_FIVE==5)
    {
        data = ((int)(rand() & 1 ? (((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) : -(((unsigned)rand()<<30) ^ ((unsigned)rand()<<15) ^ rand()) - 1));
    }
    if(STATIC_CONST_FIVE==5)
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
    if(STATIC_CONST_FIVE!=5)
    {
        printLine("message");
    }
    else
    {
        data = 7;
    }
    if(STATIC_CONST_FIVE==5)
    {
        printIntLine(100 / data);
    }
}
static void fn_005()
{
    int data;
    data = -1;
    if(STATIC_CONST_FIVE==5)
    {
        data = 7;
    }
    if(STATIC_CONST_FIVE==5)
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
