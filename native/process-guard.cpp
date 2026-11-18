// Supervise the parent process, not the short-lived Python request thread.
// PR_SET_PDEATHSIG alone follows the creating thread on Linux.
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include <poll.h>
#include <cerrno>
#include <cstdlib>
#include <cstdio>
static volatile sig_atomic_t stopped = 0;
static void stop(int signal) { stopped = signal; }
static int reap(pid_t child, int signal) {
    kill(child,SIGKILL);
    int status=0;
    while(waitpid(child,&status,0)<0 && errno==EINTR) {}
    return 128+signal;
}
int main(int argc,char** argv) {
    if(argc<3) return 125;
    pid_t expected=static_cast<pid_t>(strtol(argv[1],nullptr,10));
    if(expected<=1 || getppid()!=expected) return 125;
    int parent=-1;
#ifdef SYS_pidfd_open
    parent=static_cast<int>(syscall(SYS_pidfd_open,expected,0));
#endif
    // The fallback also checks parent identity, so PID reuse cannot keep an orphan alive.
    if(getppid()!=expected) return 125;
    pid_t guard=getpid(),child=fork();
    if(child<0) return 125;
    if(child==0) {
        if(parent>=0) close(parent);
        // This parent is the single-threaded supervisor and lives as long as its child.
        if(prctl(PR_SET_PDEATHSIG,SIGKILL)<0 || getppid()!=guard) _exit(125);
        execvp(argv[2],argv+2);perror("popAI process guard");_exit(126);
    }
    struct sigaction action{};
    action.sa_handler=stop;sigemptyset(&action.sa_mask);
    sigaction(SIGTERM,&action,nullptr);sigaction(SIGINT,&action,nullptr);
    while(true) {
        if(stopped) return reap(child,stopped);
        int status=0;
        pid_t result=waitpid(child,&status,WNOHANG);
        if(result==child) {
            if(parent>=0) close(parent);
            return WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
        }
        if(result<0 && errno!=EINTR) return 125;
        if(parent>=0) {
            pollfd descriptor{parent,POLLIN,0};
            int ready=poll(&descriptor,1,50);
            if(ready>0 && descriptor.revents) return reap(child,SIGKILL);
        } else {
            if(getppid()!=expected || kill(expected,0)<0) return reap(child,SIGKILL);
            poll(nullptr,0,50);
        }
    }
}
