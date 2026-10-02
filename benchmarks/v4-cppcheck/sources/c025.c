int f(int argc) {
    int quotient, remainder;
    remainder = argc % 2;
    argc = 2;
    quotient = argc;
    if (quotient != 0) 
        return quotient;
    return remainder;
}
