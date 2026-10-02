int subject(int x) {
    if(x<0 || x>=8) return 0;
    int d=0;
    if(x%2 >= 1) d+=1; else d-=1;
    if(x%4 >= 2) d+=2; else d-=2;
    if(x%8 >= 4) d+=4; else d-=4;
    return 100/(2*d-(-5));
}
