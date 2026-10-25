import math

def inv(a): return math.tan(a)-a

def gear_points(m, z, alpha_deg=20.0, internal=False, n_flank=4, arc_pts=1):
    r = m*z/2.0
    rb = r*math.cos(math.radians(alpha_deg))
    if internal:
        rr = r + 1.25*m   # root (major) radius
        rt = r - m        # tip (minor) radius
    else:
        rr = r - 1.25*m
        rt = r + m
    invp = inv(math.acos(rb/r))
    def phi(rho):
        a = math.acos(max(-1.0, min(1.0, rb/rho)))
        return math.pi/(2*z) + invp - inv(a)
    pts=[]; step=2*math.pi/z
    for i in range(z):
        th=i*step
        radii=[rr+(rt-rr)*k/(n_flank-1) for k in range(n_flank)]
        for rho in radii:  # left flank root->tip
            ph=phi(rho); pts.append((rho*math.cos(th-ph), rho*math.sin(th-ph)))
        ph=phi(rt)
        for k in range(1, arc_pts+1):
            a=th-ph + (2*ph)*k/(arc_pts+1); pts.append((rt*math.cos(a), rt*math.sin(a)))
        for rho in reversed(radii):  # right flank tip->root
            ph=phi(rho); pts.append((rho*math.cos(th+ph), rho*math.sin(th+ph)))
        ph=phi(rr); nxt=th+step
        a0=th+ph; a1=nxt-ph
        if a1<a0: a1+=2*math.pi
        for k in range(1, arc_pts+1):
            a=a0+(a1-a0)*k/(arc_pts+1); pts.append((rr*math.cos(a), rr*math.sin(a)))
    return pts

def area(points):
    s=0.0
    for (x1,y1),(x2,y2) in zip(points, points[1:]+points[:1]):
        s += x1*y2 - x2*y1
    return abs(s)/2.0
