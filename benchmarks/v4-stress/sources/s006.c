int subject(int x) {
  int d=0;
  if(x<0 || x>=512) return 0;
  if(x%64>=32) d+=14; else d-=14;
  if(x%32>=16) d+=7; else d-=7;
  if(x%2>=1) d+=15; else d-=15;
  if(x%128>=64) d+=24; else d-=24;
  if(x%8>=4) d+=7; else d-=7;
  if(x%16>=8) d+=22; else d-=22;
  if(x%4>=2) d+=25; else d-=25;
  if(x%512>=256) d+=18; else d-=18;
  if(x%256>=128) d+=11; else d-=11;
  return 100/(2*d-(3));
}
