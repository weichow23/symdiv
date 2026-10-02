int rand(void);
void printIntLine(int value);
void printLine(const char *value);
static const int STATIC_CONST_FIVE = 5;
void fn_001()
{
    int data;
    data = -1;
    if(STATIC_CONST_FIVE==5)
    {
        data = 0;
    }
    if(STATIC_CONST_FIVE==5)
    {
        printIntLine(100 / data);
    }
}
