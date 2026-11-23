#define _POSIX_C_SOURCE 200809L
#define MINIMP3_IMPLEMENTATION
#define MINIMP3_ONLY_MP3
#include "esphome_playback.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <mbedtls/platform_util.h>
#include <mbedtls/x509_crt.h>
/* Streaming cache: bytes arrive and are played while the body is still on the
 * wire, so the transfer is no longer paced by the daemon's 10 ms tick and a
 * lazily synthesised reply starts speaking after its first frames, not after
 * its last. DNS uses a bounded IPv4 UDP transaction, not blocking libc
 * resolution or a worker process. */
#define CHUNK_SIZE SIZE_MAX
#define CHUNK_CRLF (SIZE_MAX-1)
/* Consumed payload is dropped before the window can reach the body cap. */
#define ESP_PLAY_WINDOW (64U*1024U)
/* The engine drains the bus into a 2 x 2048-frame ring (85 ms) before its
 * write blocks, so a 100 ms lead left less than one period queued and the
 * engine ended and restarted the session at period boundaries: audible chops
 * mid-reply. Ring (85) + two periods (85) + poll and tick jitter (~40) + margin. */
#define ESP_PLAY_LEAD_MS 250
static unsigned u16(const unsigned char *p){return p[0]|((unsigned)p[1]<<8);}
static uint32_t u32(const unsigned char *p){return u16(p)|((uint32_t)u16(p+2)<<16);}
static unsigned be16(const unsigned char *p){return ((unsigned)p[0]<<8)|p[1];}
/* The bundle is a few hundred kilobytes of PEM; parsing it per reply is a
 * visible slice of a turn on a 1 GHz A35. esphomed is single threaded and keeps
 * its TLS context for the whole turn, so one process-wide chain is enough. */
static mbedtls_x509_crt playback_ca;
static int playback_ca_state;
static int ca_load(const char *path){if(!playback_ca_state){mbedtls_x509_crt_init(&playback_ca);playback_ca_state=mbedtls_x509_crt_parse_file(&playback_ca,path)?-1:1;}return playback_ca_state<0?-1:0;}
void esp_playback_init(struct esp_playback *p){memset(p,0,sizeof *p);p->fd=p->bus_fd=p->dns_fd=-1;p->chunk_left=CHUNK_SIZE;mbedtls_ssl_init(&p->ssl);mbedtls_ssl_config_init(&p->config);mbedtls_entropy_init(&p->entropy);mbedtls_ctr_drbg_init(&p->rng);}
void esp_playback_close(struct esp_playback *p){if(p->fd>=0)close(p->fd);if(p->bus_fd>=0)close(p->bus_fd);if(p->dns_fd>=0)close(p->dns_fd);mbedtls_ssl_free(&p->ssl);mbedtls_ssl_config_free(&p->config);mbedtls_ctr_drbg_free(&p->rng);mbedtls_entropy_free(&p->entropy);p->fd=p->bus_fd=p->dns_fd=-1;p->state=0;p->fetching=0;}
int esp_playback_poll_fd(const struct esp_playback *p){if(p->state==1)return p->dns_fd;if(p->state>=2&&p->state<=5)return p->fd;if(p->state==6&&p->fetching)return p->fd;{if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}}
static int tls_send(void *ctx,const unsigned char *buf,size_t n){int fd=*(int*)ctx;ssize_t w=send(fd,buf,n,MSG_DONTWAIT|MSG_NOSIGNAL);if(w<0&&(errno==EAGAIN||errno==EWOULDBLOCK))return MBEDTLS_ERR_SSL_WANT_WRITE;return w<0?MBEDTLS_ERR_SSL_INTERNAL_ERROR:(int)w;}
static int tls_recv(void *ctx,unsigned char *buf,size_t n){int fd=*(int*)ctx;ssize_t w=recv(fd,buf,n,MSG_DONTWAIT);if(w<0&&(errno==EAGAIN||errno==EWOULDBLOCK))return MBEDTLS_ERR_SSL_WANT_READ;return w<0?MBEDTLS_ERR_SSL_INTERNAL_ERROR:(int)w;}
static int connect_ip(struct esp_playback *p,struct in_addr ip){struct sockaddr_in a;memset(&a,0,sizeof a);a.sin_family=AF_INET;a.sin_port=htons((uint16_t)p->port);a.sin_addr=ip;p->fd=socket(AF_INET,SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);if(p->fd<0){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}if(connect(p->fd,(struct sockaddr*)&a,sizeof a)<0&&errno!=EINPROGRESS){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->state=2;return 0;}
static int dns_start(struct esp_playback *p){struct sockaddr_in a;FILE *f;char line[512],server[64]="";size_t z=12;const char *s=p->host,*dot;
 f=fopen("/etc/resolv.conf","r");if(!f){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}while(fgets(line,sizeof line,f)){if(sscanf(line,"nameserver %63s",server)==1)break;}fclose(f);
 memset(&a,0,sizeof a);a.sin_family=AF_INET;a.sin_port=htons(53);if(inet_pton(AF_INET,server,&a.sin_addr)!=1){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
 p->dns_id=(uint16_t)(p->deadline^(unsigned)getpid());memset(p->dns_query,0,12);p->dns_query[0]=(unsigned char)(p->dns_id>>8);p->dns_query[1]=(unsigned char)p->dns_id;p->dns_query[2]=1;p->dns_query[5]=1;
 do{dot=strchr(s,'.');size_t n=dot?(size_t)(dot-s):strlen(s);if(!n||n>63||z+n+6>sizeof p->dns_query){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->dns_query[z++]=(unsigned char)n;memcpy(p->dns_query+z,s,n);z+=n;s=dot?dot+1:NULL;}while(s);
 p->dns_query[z++]=0;p->dns_query[z++]=0;p->dns_query[z++]=1;p->dns_query[z++]=0;p->dns_query[z++]=1;p->dns_query_len=z;
 p->dns_fd=socket(AF_INET,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);if(p->dns_fd<0||connect(p->dns_fd,(struct sockaddr*)&a,sizeof a)<0||send(p->dns_fd,p->dns_query,z,MSG_DONTWAIT)!=(ssize_t)z){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->state=1;return 0;
}
static int dns_name(const unsigned char *b,size_t n,size_t *pos){for(unsigned labels=0;labels<128;labels++){if(*pos>=n){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}unsigned z=b[(*pos)++];if(!z)return 0;if((z&192)==192){if(*pos>=n){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}(*pos)++;return 0;}if(z>63||z>n-*pos){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}*pos+=z;}{if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}}
static int dns_tick(struct esp_playback *p){unsigned char b[1024];ssize_t n=recv(p->dns_fd,b,sizeof b,MSG_DONTWAIT);size_t z=12;struct in_addr ip;if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK))return 0;if(n<12||be16(b)!=p->dns_id||(b[3]&15)||!(b[2]&128)||be16(b+4)!=1||be16(b+6)>32){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
 if(dns_name(b,(size_t)n,&z)||z+4>(size_t)n){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}z+=4;for(unsigned i=0;i<be16(b+6);i++){if(dns_name(b,(size_t)n,&z)||z+10>(size_t)n){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}unsigned t=be16(b+z),cl=be16(b+z+2),len=be16(b+z+8);z+=10;if(z+len>(size_t)n){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}if(t==1&&cl==1&&len==4){memcpy(&ip,b+z,4);close(p->dns_fd);p->dns_fd=-1;return connect_ip(p,ip);}z+=len;}{if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
}
int esp_playback_start(struct esp_playback *p,const char *url,const char *bus,const char *ca,uint64_t now){const char *s,*slash,*colon;size_t host_n;struct in_addr ip;char hostport[280];
 if(p->state){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}esp_playback_close(p);esp_playback_init(p);
 if(!strncmp(url,"http://",7)){s=url+7;p->port=80;}else if(!strncmp(url,"https://",8)){s=url+8;p->port=443;p->tls=1;}else {if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
 for(const char *v=s;*v;v++)if((unsigned char)*v<33||(unsigned char)*v>126||*v=='@'||*v=='\\'||*v=='#'){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
 slash=strchr(s,'/');host_n=slash?(size_t)(slash-s):strlen(s);if(!host_n||host_n>=sizeof hostport||strlen(bus)>=sizeof p->bus){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}memcpy(hostport,s,host_n);hostport[host_n]=0;
 colon=strchr(hostport,':');if(colon){char *end;unsigned long port=strtoul(colon+1,&end,10);if(!colon[1]||*end||port<1||port>65535){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->port=(unsigned)port;host_n=(size_t)(colon-hostport);}
 if(!host_n||host_n>=sizeof p->host){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}memcpy(p->host,hostport,host_n);p->host[host_n]=0;
 for(size_t i=0;i<host_n;i++)if(!(p->host[i]=='.'||p->host[i]=='-'||(p->host[i]>='0'&&p->host[i]<='9')||(p->host[i]>='a'&&p->host[i]<='z')||(p->host[i]>='A'&&p->host[i]<='Z'))){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
 if(slash&&strlen(slash)>=sizeof p->path){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}snprintf(p->path,sizeof p->path,"%s",slash?slash:"/");snprintf(p->bus,sizeof p->bus,"%s",bus);
 int n=snprintf(p->request,sizeof p->request,"GET %s HTTP/1.1\r\nHost: %s:%u\r\nConnection: close\r\nAccept: audio/wav, audio/mpeg\r\n\r\n",p->path,p->host,p->port);if(n<0||(size_t)n>=sizeof p->request){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->request_len=(size_t)n;p->expected=SIZE_MAX;p->deadline=now+15000;p->fetching=1;
 if(p->tls){if(!ca)ca="/etc/ssl/certs/ca-certificates.crt";if(ca_load(ca)||mbedtls_ctr_drbg_seed(&p->rng,mbedtls_entropy_func,&p->entropy,(const unsigned char*)"libreecho-https",14)||mbedtls_ssl_config_defaults(&p->config,MBEDTLS_SSL_IS_CLIENT,MBEDTLS_SSL_TRANSPORT_STREAM,MBEDTLS_SSL_PRESET_DEFAULT)){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}mbedtls_ssl_conf_authmode(&p->config,MBEDTLS_SSL_VERIFY_REQUIRED);mbedtls_ssl_conf_ca_chain(&p->config,&playback_ca,NULL);mbedtls_ssl_conf_rng(&p->config,mbedtls_ctr_drbg_random,&p->rng);if(mbedtls_ssl_setup(&p->ssl,&p->config)||mbedtls_ssl_set_hostname(&p->ssl,p->host)){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}mbedtls_ssl_set_bio(&p->ssl,&p->fd,tls_send,tls_recv,NULL);}
 if(inet_pton(AF_INET,p->host,&ip)==1)return connect_ip(p,ip);return dns_start(p);
}
static int headers(struct esp_playback *p){size_t i;for(i=0;i+3<p->received&&i<8192;i++)if(!memcmp(p->buffer+i,"\r\n\r\n",4))break;if(i+3>=p->received)return p->received>=8192?-1:0;
 if(i+4>8192||memchr(p->buffer,0,i+4)){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}char h[8193];memcpy(h,p->buffer,i+4);h[i+4]=0;if(strncmp(h,"HTTP/1.1 200 ",13)&&strncmp(h,"HTTP/1.0 200 ",13)){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
 char *line=strstr(h,"\r\n")+2;int have_len=0;while(*line&&strncmp(line,"\r\n",2)){char *end=strstr(line,"\r\n");if(!end){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}*end=0;
 if(!strncasecmp(line,"Content-Length:",15)){char *v=line+15,*q;while(*v==' ')v++;if(have_len++||*v<'0'||*v>'9'){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}unsigned long long z=strtoull(v,&q,10);if(*q||z>ESP_PLAY_BODY_MAX){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->expected=(size_t)z;}
 if(!strncasecmp(line,"Transfer-Encoding:",18)){char *v=line+18;while(*v==' ')v++;if(p->chunked||strcasecmp(v,"chunked")){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->chunked=1;}
 if(!strncasecmp(line,"Content-Encoding:",17)){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}line=end+2;}
 if(p->chunked&&have_len){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
 if(p->chunked)p->chunk_left=CHUNK_SIZE;
 p->body_start=i+4;p->header_done=1;return 1;
}
/* HA streams TTS lazily, so a chunked body is de-framed as it arrives instead
 * of at EOF: payload is compacted to buffer[body_start..body_start+body_len)
 * and the still-unparsed wire bytes move behind it, which keeps the window
 * bounded while a chunk line can still be split across reads. */
static int dechunk(struct esp_playback *p){unsigned char *b=p->buffer;size_t r=p->body_start+p->body_len,w=r,n=p->received;
 if(!p->chunked)return 0;
 while(r<n){
  if(p->chunk_left==CHUNK_SIZE){size_t z=0;unsigned long long len=0;
   while(r<n&&b[r]!='\r'&&z<16){unsigned c=b[r],v;if(c>='0'&&c<='9')v=c-'0';else if(c>='a'&&c<='f')v=c-'a'+10;else if(c>='A'&&c<='F')v=c-'A'+10;else {if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}len=len*16+v;r++;z++;}
   if(r==n)break;
   if(!z||r+2>n||b[r]!='\r'||b[r+1]!='\n'){fprintf(stderr,"DBG dechunk-crlf z=%zu r=%zu n=%zu\n",z,r,n);esphome_fail_line=__LINE__;return -1;}r+=2;
   if(len>ESP_PLAY_BODY_MAX){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
   if(!len){
    for(;;){if(r+2>n)break;if(b[r]=='\r'&&b[r+1]=='\n'){r+=2;p->eof=1;break;}size_t e=r;while(e+1<n&&(b[e]!='\r'||b[e+1]!='\n'))e++;if(e+1>=n)break;if(e-r>8192||!memchr(b+r,':',e-r)){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}r=e+2;}
    if(!p->eof)break;
    if(r!=n){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
    break;
   }
   p->chunk_left=(size_t)len;
  }
  if(p->chunk_left==CHUNK_CRLF){if(r+2>n)break;if(b[r]!='\r'||b[r+1]!='\n'){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}r+=2;p->chunk_left=CHUNK_SIZE;continue;}
  {size_t take=n-r;if(take>p->chunk_left)take=p->chunk_left;memmove(b+w,b+r,take);w+=take;r+=take;p->chunk_left-=take;if(!p->chunk_left)p->chunk_left=CHUNK_CRLF;}
 }
 p->body_len=w-p->body_start;
 if(w!=r)memmove(b+w,b+r,n-r);
 p->received=w+(n-r);
 return 0;
}
/* Called whenever the format may be known. Starts the FIFO as soon as the WAV
 * header plus first samples (or the first MP3 frames) are in, so the rest of
 * the body plays while it downloads. Returns 0 while more bytes are needed,
 * 1 when playing, -1 when the stream is invalid. A completed body (p->eof) is
 * still validated strictly against its own chunk sizes. */
static int prepare(struct esp_playback *p,uint64_t now){unsigned char *b=p->buffer+p->body_start;size_t n=p->body_len,z=12;int fmt=0,data=0;
 if(n>ESP_PLAY_BODY_MAX){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
 if(!n)return p->eof?-1:0;
 if(n>=12&&!memcmp(b,"RIFF",4)&&!memcmp(b+8,"WAVE",4)){p->wav=1;
  if(p->eof&&u32(b+4)!=UINT32_MAX&&u32(b+4)!=n-8){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
  while(z+8<=n){size_t l=u32(b+z+4),start=z+8;
   if(!memcmp(b+z,"fmt ",4)){if(l<16){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}if(start+16>n)return p->eof?-1:0;if(u16(b+start)!=1||u16(b+start+14)!=16){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->channels=(int)u16(b+start+2);p->rate=(int)u32(b+start+4);if(p->channels<1||p->channels>2||p->rate<8000||p->rate>48000||u16(b+start+12)!=(unsigned)p->channels*2){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}fmt=1;}
   else if(!memcmp(b+z,"data",4)){
    /* ffmpeg's non-seekable writer leaves 0xFFFFFFFF, and 0 x what it could not
     * patch; both mean "until EOF" while the reply is still streaming. */
    p->pcm_offset=start;
    if(!p->eof){p->pcm_bytes=(l==UINT32_MAX||!l)?SIZE_MAX:l;data=1;break;}
    if(l==UINT32_MAX)l=n-start;
    p->pcm_bytes=l;data=1;
   }
   if(l>n-start||((l&1)&&l==n-start))return p->eof?-1:0;
   z=start+l+(l&1);
  }
  if(!fmt||!data)return p->eof?-1:0;
  if(p->eof){
   if(p->pcm_offset+p->pcm_bytes>n||z!=n){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
   if(p->pcm_bytes%(2*(size_t)p->channels)){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
  }else{
   if(n<=p->pcm_offset)return 0; /* wait for the first sample, not silence */
   if(p->pcm_bytes!=SIZE_MAX&&p->pcm_bytes%(2*(size_t)p->channels)){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
  }
  p->position=p->pcm_offset;
 }else{
  if(n<4&&!p->eof)return 0;
  mp3dec_init(&p->decoder);
  if(n>=10&&!memcmp(b,"ID3",3)){if((b[6]|b[7]|b[8]|b[9])&128){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->position=10+((size_t)b[6]<<21)+((size_t)b[7]<<14)+((size_t)b[8]<<7)+b[9];if(p->position>=n)return p->eof?-1:0;}
  if(n<512&&!p->eof)return 0;
 }
 le_radio_resample_reset(&p->resampler);p->bus_fd=open(p->bus,O_WRONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW);if(p->bus_fd<0){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->origin=now;p->deadline=now+120000;p->state=6;return 1;
}
/* One bounded pass of network work: read what the socket has, de-frame it and
 * start playback the moment the format is decodable. The poll loop must not
 * pace a lazily synthesised body at one 8 KiB read per 10 ms tick. */
static int fetch(struct esp_playback *p,uint64_t now){
 for(unsigned reads=0;reads<16&&p->fd>=0;reads++){
  size_t cap=sizeof p->buffer-p->received;if(!cap){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}if(cap>8192)cap=8192;
  int rc=p->tls?mbedtls_ssl_read(&p->ssl,p->buffer+p->received,cap):tls_recv(&p->fd,p->buffer+p->received,cap);
  if(rc==MBEDTLS_ERR_SSL_WANT_READ||rc==MBEDTLS_ERR_SSL_WANT_WRITE)return 0;
  if(rc==MBEDTLS_ERR_SSL_PEER_CLOSE_NOTIFY)rc=0;
  if(rc<0){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
  if(!rc){
   if(p->chunked){if(!p->eof){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}}
   else{p->body_len=p->received-p->body_start;if(p->expected!=SIZE_MAX&&p->body_len!=p->expected){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->eof=1;}
   close(p->fd);p->fd=-1;p->fetching=0;break;
  }
  p->received+=(size_t)rc;
  if(!p->header_done){int h=headers(p);if(h<0){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}if(!h){if(p->received>=sizeof p->buffer-8192){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}continue;}}
  if(p->chunked){if(dechunk(p)<0){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}if(p->eof){close(p->fd);p->fd=-1;p->fetching=0;break;}}else p->body_len=p->received-p->body_start;
  if(p->body_len>ESP_PLAY_BODY_MAX){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
  if(!p->chunked&&p->expected!=SIZE_MAX){
   if(p->body_len>p->expected){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}
   if(p->body_len==p->expected){p->eof=1;close(p->fd);p->fd=-1;p->fetching=0;break;}
  }
  if(p->state==5){int r=prepare(p,now);if(r<0){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}if(r>0)return 1;}
 }
 if(p->state==5&&p->eof){int r=prepare(p,now);if(r<0){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}if(r>0)return 1;}
 return 0;
}
/* Drop payload already decoded so a long streaming body stays inside the
 * buffer; the data offset only matters until the first consumed byte. */
static void compact(struct esp_playback *p){size_t drop=p->body_start+p->position;if(drop<=p->body_start)return;memmove(p->buffer,p->buffer+drop,p->received-drop);p->received-=drop;p->body_len-=p->position;p->body_start=0;p->pcm_offset=0;p->position=0;}
/* Network behind real time mid-announcement: keep the fifo ahead with silence
 * instead of letting the engine see an underrun and reopen the PCM. */
static int pad_silence(struct esp_playback *p,uint64_t now){if(!p->frames||!p->source_rate)return 0;uint64_t want=(now-p->origin+ESP_PLAY_LEAD_MS)*48;if(p->frames>=want)return 0;uint64_t left=want-p->frames;if(left>2048)left=2048;
 size_t in=(size_t)(left*(unsigned)p->source_rate/48000)+2;short silence[2048*2];if(in>1024)in=1024;memset(silence,0,in*4);
 int n=le_radio_resample(&p->resampler,silence,(int)in,2,p->source_rate,p->output,4096);if(n<=0){if(!esphome_fail_line)esphome_fail_line=__LINE__;return -1;}p->output_len=(size_t)n*4;p->output_sent=0;return 0;}
static int tick_once(struct esp_playback *p,uint64_t now){int rc;ssize_t got;unsigned char *b;if(!p->state)return p->result? p->result:-1;if(now>p->deadline){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}
 if(p->state==1){if(dns_tick(p)<0){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}return 0;}
 if(p->state==2){struct sockaddr_in a;socklen_t n=sizeof a;if(getpeername(p->fd,(struct sockaddr*)&a,&n)<0){int err=0;n=sizeof err;if(getsockopt(p->fd,SOL_SOCKET,SO_ERROR,&err,&n)<0||err){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}return 0;}p->state=p->tls?3:4;}
 if(p->state==3){rc=mbedtls_ssl_handshake(&p->ssl);if(rc==MBEDTLS_ERR_SSL_WANT_READ||rc==MBEDTLS_ERR_SSL_WANT_WRITE)return 0;if(rc||mbedtls_ssl_get_verify_result(&p->ssl)){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}p->state=4;}
 if(p->state==4){size_t left=p->request_len-p->request_sent;rc=p->tls?mbedtls_ssl_write(&p->ssl,(unsigned char*)p->request+p->request_sent,left):tls_send(&p->fd,(unsigned char*)p->request+p->request_sent,left);if(rc==MBEDTLS_ERR_SSL_WANT_READ||rc==MBEDTLS_ERR_SSL_WANT_WRITE)return 0;if(rc<=0){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}p->request_sent+=(size_t)rc;if(p->request_sent==p->request_len)p->state=5;return 0;}
 if(p->state==5)return fetch(p,now)<0?-1:0;
 if(p->state==7){int remaining=0;if(now<p->drain_until)return 0;if(ioctl(p->bus_fd,FIONREAD,&remaining)==0&&remaining>0)return 0;p->result=1;esp_playback_close(p);return 1;}
 if(p->state!=6){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}
 if(p->fetching&&fetch(p,now)<0){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}
 if(p->output_sent<p->output_len){if(p->frames*1000/48000>now-p->origin+ESP_PLAY_LEAD_MS)return 0;got=write(p->bus_fd,(unsigned char*)p->output+p->output_sent,p->output_len-p->output_sent);if(got<0&&(errno==EAGAIN||errno==EWOULDBLOCK))return 0;if(got<=0){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}p->output_sent+=(size_t)got;if(p->output_sent<p->output_len)return 0;p->frames+=p->output_len/4;p->output_len=p->output_sent=0;return 0;}
 b=p->buffer+p->body_start;size_t end=p->wav?(p->pcm_bytes==SIZE_MAX?p->body_len:p->position+p->pcm_bytes):p->body_len;
 if(p->position>=end){
  if(p->fetching)return pad_silence(p,now);
  if(!p->frames||!p->source_rate){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}
  uint64_t desired=(p->input_frames*48000+(unsigned)p->source_rate-1)/(unsigned)p->source_rate;
  if(p->frames<desired){uint64_t left=desired-p->frames;if(left>32){fprintf(stderr,"DBG tail-biggap frames=%llu input=%llu desired=%llu rate=%d fetching=%d eof=%d position=%zu body_len=%zu pcm_bytes=%zu\n",(unsigned long long)p->frames,(unsigned long long)p->input_frames,(unsigned long long)desired,p->source_rate,p->fetching,p->eof,p->position,p->body_len,p->pcm_bytes);if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}short pad[6];for(unsigned i=0;i<3;i++){pad[2*i]=p->resampler.history[4];pad[2*i+1]=p->resampler.history[5];}int tail=le_radio_resample(&p->resampler,pad,3,2,p->source_rate,p->output,(int)left);if(tail<=0){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}p->output_len=(size_t)tail*4;p->output_sent=0;return 0;}
  p->state=7;p->drain_until=p->origin+(p->frames*1000+47999)/48000+40;return 0;
 }
 {short pcm[MINIMP3_MAX_SAMPLES_PER_FRAME];int frames,channels,rate;
 if(p->wav){size_t endb=p->body_len;if(p->pcm_bytes!=SIZE_MAX&&endb>end)endb=end;if(p->position>=endb){if(p->fetching)return 0;{if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}}size_t bytes=endb-p->position;size_t count=bytes/(2*(size_t)p->channels);if(!count){if(p->fetching)return 0;{if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}}if(count>1024)count=1024;for(size_t i=0;i<count*(size_t)p->channels;i++)pcm[i]=(short)u16(b+p->position+2*i);p->position+=count*2*p->channels;if(p->pcm_bytes!=SIZE_MAX)p->pcm_bytes-=count*2*p->channels;frames=(int)count;channels=p->channels;rate=p->rate;}
 else{mp3dec_frame_info_t info;size_t left=end-p->position;frames=mp3dec_decode_frame(&p->decoder,b+p->position,(int)(left>65536?65536:left),pcm,&info);if(info.frame_bytes<=0||(size_t)info.frame_bytes>left){if(p->fetching)return 0;{if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}}p->position+=(size_t)info.frame_bytes;if(!frames)return 0;channels=info.channels;rate=info.hz;if(rate<8000||rate>48000||channels<1||channels>2){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}}
 if(p->fetching&&p->position>ESP_PLAY_WINDOW)compact(p);
 if(p->source_rate&&p->source_rate!=rate){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}p->source_rate=rate;p->input_frames+=(unsigned)frames;rc=le_radio_resample(&p->resampler,pcm,frames,channels,rate,p->output,8192);if(rc<=0){if(!esphome_fail_line)esphome_fail_line=__LINE__;goto fail;}p->output_len=(size_t)rc*4;p->output_sent=0;return 0;}
 fail:p->result=-1;esp_playback_close(p);return -1;
}
/* One decode step (one MP3 frame or <=1024 WAV frames) and its bus write
 * happen on separate tick_once() calls. At 22.05 kHz that is only 13-46 ms of
 * 48 kHz output per two calls, while esphomed's poll loop runs every ~20 ms on
 * a HZ=100 kernel, so a single step per daemon tick fell behind real time and
 * the engine closed and reopened the PCM every couple of seconds. Keep
 * stepping until the pacing lead is full, the bus would block or the state
 * changes; the step bound keeps one tick from monopolising the loop. */
int esp_playback_tick(struct esp_playback *p,uint64_t now){int playing=p->state==6,rc=tick_once(p,now);
 /* Only an already-playing slot catches up; fetch/prepare transitions keep
  * their one-step-per-tick behaviour. */
 for(unsigned step=0;playing&&!rc&&p->state==6&&step<64;step++){size_t position=p->position,sent=p->output_sent,len=p->output_len;uint64_t frames=p->frames;
  rc=tick_once(p,now);if(!rc&&p->state==6&&p->position==position&&p->output_sent==sent&&p->output_len==len&&p->frames==frames)break;}
 return rc;
}
