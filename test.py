import cv2
import numpy as np
import os
from scipy.optimize import least_squares
import copy
import open3d as o3d
from tqdm import tqdm
import matplotlib.pyplot as plt

def feat_to_tracks(kp, hs):
	#print(kp.shape, poses.shape)
	tot_corrs = hs.shape[0]
	i = 0
	track_pts = np.array(kp)
	while(i < tot_corrs):
		H = hs[i].reshape(3,3)
		#print(H)
		#print(kp[0])
		kp_h = cv2.convertPointsToHomogeneous(kp)[:, 0, :]
		Hinv = np.linalg.inv(H)
		kp_h = np.array([np.matmul(Hinv, kp_) for kp_ in kp_h])
		kp = cv2.convertPointsFromHomogeneous(kp_h)[:, 0, :]
		track_pts = np.hstack((kp, track_pts))
		
		i = i + 1
	return track_pts
		
	
def img_downscale(img, downscale):
	downscale = int(downscale/2)
	i = 1
	while(i <= downscale):
		img = cv2.pyrDown(img)
		i = i + 1
	return img

def ReprojectionError(cloud, poses, tracks, K):
	i = 0
	repr_error = 0
	while(i < len(poses)):
		Rt = poses[i].reshape((3,4))
		R = Rt[:3, :3]
		t = Rt[:3, 3]
		r, _ = cv2.Rodrigues(R)
		
		p = track[:, i:i + 2]
		p_reproj, _ = cv2.projectPoints(X, r, t, K, distCoeffs=None)
		p_reproj = p_reproj[:, 0, :]
		#print(X.shape, p.shape, p_reproj.shape)
		total_error = cv2.norm(p, p_reproj, cv2.NORM_L2)
		repr_error = repr_error + total_error / len(p)
		i = i + 1
	return repr_error
	
def OptimReprojectionError(x):
	Rt = x[0:12].reshape((3,4))
	K = x[12:21].reshape((3,3))
	rest = len(x[21:])
	rest = int(rest * 0.4)
	p = x[21:21 + rest].reshape((2, int(rest/2)))
	X = x[21 + rest:].reshape((int(len(x[21 + rest:])/3), 3))
	R = Rt[:3, :3]
	t = Rt[:3, 3]
	
	total_error = 0
	
	p = p.T
	num_pts = len(p)
	error = []
	r, _ = cv2.Rodrigues(R)
	
	p2d, _ = cv2.projectPoints(X, r, t, K, distCoeffs = None)
	p2d = p2d[:, 0, :]
	#print(p2d[0], p[0])
	for idx in range(num_pts):
		img_pt = p[idx]
		reprojected_pt = p2d[idx]
		er = (img_pt - reprojected_pt)**2
		error.append(er)
	
	err_arr = np.array(error).ravel()/num_pts
	
	print(np.sum(err_arr))
	#err_arr = np.sum(err_arr)
	

	return err_arr

def BundleAdjustment(cloud, poses, tracks, K):
	print(cloud.shape, poses.shape, tracks.shape)

def to_ply(path, point_cloud, colors, densify):
    out_points = point_cloud.reshape(-1, 3) * 200
    out_colors = colors.reshape(-1, 3)
    #print(out_colors.shape, out_points.shape)
    verts = np.hstack([out_points, out_colors])

    # cleaning point cloud
    mean = np.mean(verts[:, :3], axis=0)
    temp = verts[:, :3] - mean
    dist = np.sqrt(temp[:, 0] ** 2 + temp[:, 1] ** 2 + temp[:, 2] ** 2)
    #print(dist.shape, np.mean(dist))
    indx = np.where(dist < np.mean(dist) + 300)
    verts = verts[indx]
    #print( verts.shape)
    ply_header = '''ply
		format ascii 1.0
		element vertex %(vert_num)d
		property float x
		property float y
		property float z
		property uchar blue
		property uchar green
		property uchar red
		end_header
		'''
    if not densify:
        with open(path + '/Point_Cloud/sparse.ply', 'w') as f:
            f.write(ply_header % dict(vert_num=len(verts)))
            np.savetxt(f, verts, '%f %f %f %d %d %d')
    else:
        with open(path + '/Point_Cloud/isparse.ply', 'w') as f:
            f.write(ply_header % dict(vert_num=len(verts)))
            np.savetxt(f, verts, '%f %f %f %d %d %d')


cv2.namedWindow('image', cv2.WINDOW_NORMAL)
# Input Camera Intrinsic Parameters
#K = np.array([[2393.952166119461, -3.410605131648481e-13, 932.3821770809047], [0, 2398.118540286656, 628.2649953288065], [0, 0, 1]])

K = np.array([[2759.48, 0, 1520.69], [0, 2764.16, 1006.81], [0, 0, 1]])
d = np.zeros((5,1))
# Suppose if computationally heavy, then the images can be downsampled once. Note that downsampling is done in powers of two, that is, 1,2,4,8,...
downscale = 2
K[0,0] = K[0,0] / float(downscale)
K[1,1] = K[1,1] / float(downscale)
K[0,2] = K[0,2] / float(downscale)
K[1,2] = K[1,2] / float(downscale)

# Current Path Directory
path = os.getcwd()

# Input the directory where the images are kept. Note that the images have to be named in order for this particular implementation
#img_dir = path + '/Sample Dataset/'
#img_dir = '/home/arihant/Desktop/gustav/'

img_dir = '/home/arihant/Desktop/SfM_quality_evaluation/Benchmarking_Camera_Calibration_2008/fountain-P11/images/' 


Xtot = np.zeros((1, 3))
colorstot = np.zeros((1, 3))

sift = cv2.xfeatures2d.SIFT_create()
bf = cv2.BFMatcher()

img_list = sorted(os.listdir(img_dir))
images = []
for img in img_list:
    if '.jpg' in img.lower() or '.png' in img.lower():
        images = images + [img]
i = 1
#print(images)

# Acquiring the first image and detecting features using SIFT
img0 = img_downscale(cv2.imread(img_dir + '/' + images[0]), downscale)
img0gray = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
kp0, des0 = sift.detectAndCompute(img0gray, None)
print("Frame: ",i,",Total features tracked: ",len(des0))
img_tot = 10 #len(images)
feature_thresh = 20
homography = np.array([])
all_poses = np.array([])
while(i < img_tot):
	
	img1 = img_downscale(cv2.imread(img_dir + '/' + images[i]), downscale)
	img1gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
	kp1, des1 = sift.detectAndCompute(img1gray, None)
	
	matches = bf.knnMatch(des0, des1, k = 2)
	good = []
	for m, n in matches:
		if m.distance < 0.7 * n.distance:
			good.append(m)
	if i == 1:
		kp0 = np.float32([kp0[m.queryIdx].pt for m in good])
	else:
		kp0 = np.float32([kp0[m.queryIdx] for m in good])
	
	
	kp1 = np.float32([kp1[m.trainIdx].pt for m in good])
	des0 = np.float32([des0[m.queryIdx] for m in good])
	des1 = np.float32([des1[m.trainIdx] for m in good])
	
	E, mask = cv2.findEssentialMat(kp0, kp1, K, method=cv2.RANSAC, prob = 0.999, threshold = 1, mask = None)
	
	kp0 = kp0[mask.ravel() == 1]
	kp1 = kp1[mask.ravel() == 1]
	
	des0 = des0[mask.ravel() == 1]
	des1 = des1[mask.ravel() == 1]
	#if i != 1:
	#	find_common(kp1o, kp0, des1o, des0)
	
	_, R, t, mask = cv2.recoverPose(E, kp0, kp1, K)
	r, _ = cv2.Rodrigues(R)
	#print(r.shape, t.shape)
	Rt = np.vstack((r,t))
	if len(kp0) < feature_thresh:
		print("Frame: ",i+1, "Less features! Restart tracks")
		break
	else:
		print("Frame: ",i+1,",Total features tracked: ",len(kp0))
		
	H, _ = cv2.findHomography(kp0, kp1, cv2.RANSAC)
	if i == 1:
		homography = np.array(H.ravel())
		all_poses = np.array(Rt)
	else:
		homography = np.vstack((H.ravel(), homography))
		all_poses = np.hstack((all_poses, Rt))
		
	kp0 = kp1
	kp1o = kp1
	des1o = des1
	img0 = img1
	des0 = des1
	img0gray = img1gray
	cv2.imshow('image', img1)
	if cv2.waitKey(1) & 0xff == ord('q'):
		break
	i = i + 1
#print(des0)
# Output is a set of tracked feature points across 'i' images
track = feat_to_tracks(kp1, homography)
#print(track.shape, all_poses.shape, i)
cv2.destroyAllWindows()

# Triangulation
i = 0
I0 = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]])
camera_poses = np.array(I0.ravel())
P0 = np.matmul(K, I0)

kp0 = track[:, i:i + 2]
kp1 = track[:, i + 2:i + 4]
E = all_poses[:, 0]
r = E[0:3]
t = E[3:6]
R, _ = cv2.Rodrigues(r)
t = t.reshape(3,1)
Rt = np.hstack((R,t))
camera_poses = np.vstack((camera_poses, Rt.ravel()))
P1 = np.matmul(K, Rt)
cloud = cv2.triangulatePoints(P0, P1, kp0.T, kp1.T).T
X = cv2.convertPointsFromHomogeneous(cloud)[:, 0, :]
#camera_poses = np.array(P0.ravel())
#camera_poses = np.vstack((camera_poses, P1.ravel()))
while(int(i/2) < img_tot - 2):
	#print(kp[0])
	kp = track[:, i + 4:i + 6]
	#print(kp0.shape, kp.shape, kp1.shape)
	ret, rvecs, t, inliers = cv2.solvePnPRansac(X, kp, K, d, cv2.SOLVEPNP_ITERATIVE)
	R, _ = cv2.Rodrigues(rvecs)
	Rt = np.hstack((R, t))
	#print(rvecs.shape, t.shape, rt.shape)
	#print(X[0])
	#P2 = np.matmul(K, np.hstack((R,t)))
	camera_poses = np.vstack((camera_poses, Rt.ravel()))
	i = i + 2


# Finding Overall Reprojection Error
#error = ReprojectionError(X, camera_poses, track, K)
#print("Reprojection Error: ", error)
#BundleAdjustment(X, camera_poses, track, K)


# Now, we have the coordinates for all camera positions. Now, perform final triangulation.
i = 0
while(i < img_tot - 1):
	img0 = img_downscale(cv2.imread(img_dir + '/' + images[i]), downscale)
	img0gray = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
	kp0, des0 = sift.detectAndCompute(img0gray, None)
	Rt = camera_poses[i].reshape((3,4))
	P0 = np.matmul(K, Rt)
	
	img1 = img_downscale(cv2.imread(img_dir + '/' + images[i + 1]), downscale)
	img1gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
	kp1, des1 = sift.detectAndCompute(img1gray, None)
	Rt = camera_poses[i + 1].reshape((3,4))
	P1 = np.matmul(K, Rt)
	
	matches = bf.knnMatch(des0, des1, k = 2)
	good = []
	for m, n in matches:
		if m.distance < 0.7 * n.distance:
			good.append(m)
	
	kp0 = np.float32([kp0[m.queryIdx].pt for m in good])
	kp1 = np.float32([kp1[m.trainIdx].pt for m in good])
	
	#E, mask = cv2.findEssentialMat(kp0, kp1, K, method=cv2.RANSAC, prob = 0.999, threshold = 1, mask = None)
	
	#kp0 = kp0[mask.ravel() == 1]
	#kp1 = kp1[mask.ravel() == 1]
	#print(P0, P1)
	#print(P0)
	cloud = cv2.triangulatePoints(P0, P1, kp0.T, kp1.T).T
	cloud = cv2.convertPointsFromHomogeneous(cloud)[:, 0, :]
	#print(cloud.shape)
	print("Registering Pair: ",i+1)
	Xtot = np.vstack((Xtot, cloud))
	kp1_reg = np.array(kp1, dtype=np.int32)
	colors = np.array([img1[l[1], l[0]] for l in kp1_reg])
	colorstot = np.vstack((colorstot, colors))
	#print(Xtot.shape, colorstot.shape)	
	i = i + 1

print("Processing Point Cloud...")
print("Total Points in Point Cloud: ",Xtot.shape)
to_ply(path, Xtot, colorstot, densify = True)
print("Done!")


