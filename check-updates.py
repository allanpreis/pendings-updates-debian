import apt
import apt_pkg
from time import strftime
import os
import subprocess
import sys
import requests
import socket
import json

SYNAPTIC_PINFILE = "/var/lib/synaptic/preferences"
DISTRO = subprocess.check_output(["lsb_release", "-c", "-s"],
                                 universal_newlines=True).strip()


def clean(cache, depcache):
    depcache.init()


##Função que imita o ato de uma atualização, porém não faz nenhuma alteração
def saveDistUpgrade(cache, depcache):
    depcache.upgrade(True)
    if depcache.del_count > 0:
        clean(cache, depcache)
    depcache.upgrade()


##Função que retorna a lista de pacotes para atualização
def get_update_packages():
    pkgs = []

    apt_pkg.init()
    # Força ´apt to build´ para os caches em memória
    apt_pkg.config.set("Dir::Cache::pkgcache", "")

    try:
        cache = apt_pkg.Cache(apt.progress.base.OpProgress())
    except SystemError as e:
        sys.stderr.write("Error: Opening the cache (%s)" % e)
        sys.exit(-1)

    depcache = apt_pkg.DepCache(cache)
    # Lê os arquivos pin
    depcache.read_pinfile()
    # Lê os arquvios synaptic pin
    if os.path.exists(SYNAPTIC_PINFILE):
        depcache.read_pinfile(SYNAPTIC_PINFILE)
    depcache.init()

    try:
        saveDistUpgrade(cache, depcache)
    except SystemError as e:
        sys.stderr.write("Error: Marking the upgrade (%s)" % e)
        sys.exit(-1)

    # Usa os atributos devido o ´apt.Cache()´ não force o método __exit__
    # no Ubuntu 12.04 aparece que aptcache = apt.Cache()
    for pkg in cache.packages:
        if not (depcache.marked_install(pkg) or depcache.marked_upgrade(pkg)):
            continue
        inst_ver = pkg.current_ver
        cand_ver = depcache.get_candidate_ver(pkg)
        if cand_ver == inst_ver:
            continue
        record = {"name": pkg.name,
                  "security": isSecurityUpgrade(pkg, depcache),
                  ##"section": pkg.section,
                  "current_version": inst_ver.ver_str if inst_ver else '-',
                  "candidate_version": cand_ver.ver_str if cand_ver else '-',
                  "priority": cand_ver.priority_str}
        pkgs.append(record)

    return pkgs


def isSecurityUpgrade(pkg, depcache):
    # Função que verifica se a versão apresentada é uma atualização de seguranção, senão irá mascarar uma
    def isSecurityUpgrade_helper(ver):
        security_pockets = [("Ubuntu", "%s-security" % DISTRO),
                            ("gNewSense", "%s-security" % DISTRO),
                            ("Debian", "%s-updates" % DISTRO)]

        for (file, index) in ver.file_list:
            for origin, archive in security_pockets:
                if (file.archive == archive and file.origin == origin):
                    return True
        return False

    inst_ver = pkg.current_ver
    cand_ver = depcache.get_candidate_ver(pkg)

    if isSecurityUpgrade_helper(cand_ver):
        return True

    # Verfica se há atualização de segurança que são mascardas por uma versão de outro repositório (-proposed ou -update)
    for ver in pkg.version_list:
        if (inst_ver and
                apt_pkg.version_compare(ver.ver_str, inst_ver.ver_str) <= 0):
            continue
        if isSecurityUpgrade_helper(ver):
            return True

    return False


##Função que imprimi as atualizações de pacotes em uma tabela
def print_result(pkgs):
    security_updates = list(filter(lambda x: x.get('security'), pkgs))
    text = list()
    hostname = socket.gethostname()
    text.append('Check Time: %s' % strftime('%m/%d/%Y %H:%M:%S'))
    if not pkgs:
        text.append('No available updates on this machine.')
    else:
        # Updates disponiveis em tabela
        text.append('Server: %s' % hostname)
        text.append('\n%d packages can be updated.' % len(pkgs))

        ##Print com detalhes sobre o nome do pacote, versão, updates de segurança e versão atual do pacote
        text.append('%d updates are security updates.' % len(security_updates))
        text.append('-' * 100)
        # Lista os pacotes de segurança disponiveis
        text.append('Package Name'.ljust(20) +
                    'Current Version'.ljust(20) +
                    'Latest Version'.ljust(20) +
                    'Security'.ljust(10))
        text.append('-' * 100)
        for pkg in pkgs:
            text.append('{:<15}{:<25}{:<15}{:<15}'.format(pkg.get('name'),
                pkg.get('current_version'),
                pkg.get('candidate_version'),
                '*' if pkg.get('security') else ''))
    return '\n'.join(text)


##Resultado no Terminal
if __name__ == '__main__':
    pkgs = get_update_packages()
    print(print_result(pkgs))

##Enviar o resultado para um bot do Telegram
if __name__ == '__main__':
    pkgs = get_update_packages()
    available_updates = print_result(pkgs)

    bot_token = '1360909421:AAHTwZaF4I7UAe5JyR72Wjz_FZS4C_xPRMc'
    bot_chatID = '-512778645'

    send_text = 'https://api.telegram.org/bot' + bot_token + '/sendMessage?chat_id=' + bot_chatID + '&parse_mode=Markdown&text=' + available_updates
    response = requests.post(send_text, headers={'Content-Type': 'application/json'})
    print('%s - %s' % (response.status_code, response.text))
