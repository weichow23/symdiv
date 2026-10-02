int rand(void);
void printIntLine(int value);
void printLine(const char *value);
void fn_001()
{
    int i,j;
    int data;
    data = -1;
    for(i = 0; i < 1; i++)
    {
        data = 0;
    }
    for(j = 0; j < 1; j++)
    {
        printIntLine(100 / data);
    }
}
