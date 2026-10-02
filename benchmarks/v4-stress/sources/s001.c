int subject(int x0,int x1,int x2,int x3,int x4,int x5,int x6,int x7,int x8) {
  int d=0;
  if(x0%3==1) d+=9; else d-=9;
  if(x1%3==1) d+=12; else d-=12;
  if(x2%3==1) d+=13; else d-=13;
  if(x3%3==1) d+=28; else d-=28;
  if(x4%3==1) d+=18; else d-=18;
  if(x5%3==1) d+=20; else d-=20;
  if(x6%3==1) d+=24; else d-=24;
  if(x7%3==1) d+=22; else d-=22;
  if(x8%3==1) d+=14; else d-=14;
  return 100/(d-(16));
}
