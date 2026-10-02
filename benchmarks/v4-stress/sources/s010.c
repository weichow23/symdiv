int rand(void);
int subject(void) {
  int d=0, w=2;
  for(int i=0;i<7;i++) {
    int x=rand();
    if(x%3==1) d+=w; else d-=w;
    w+=3;
  }
  return 100/(2*d-(-77));
}
