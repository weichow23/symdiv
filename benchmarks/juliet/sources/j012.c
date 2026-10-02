int rand(void);
void printIntLine(int value);
void printLine(const char *value);
void fn_001()
{
    int data;
    data = -1;
    data = 0;
    {
        int dataCopy = data;
        int data = dataCopy;
        printIntLine(100 % data);
    }
}
