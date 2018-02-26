from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
from OpenGL.GL.shaders import *
from colour import Color
from threading import Thread
from random import randint
from ctypes import sizeof
from numpy import ones, clip
from math import sin, cos, pow, pi
import json
import time

class LedVisualizer:
    """
    Simulates the LED cube in different configurations in OpenGL.
    You have to provide a json dictionary at instantiation, this should refer to a json file.
    You also have to provide a pointer to the array of led colors.
    After this, use the refresh function to update the LEDs.
    The current shader supports up to 300 LEDS, update the shader variable if more is needed.
    """

    model = None
    program = None
    led_colors = None
    visualizer_thread = None

    vao = None

    led_enclosure_buffer = None
    led_enclosure_buffer_id = None
    attrib_position_id = None

    led_color_buffer = None
    led_color_buffer_id = None
    attrib_led_color_id = None

    led_position_buffer = None
    led_position_buffer_id = None
    attrib_led_position_id = None

    camera_horizontal_angle = pi/4
    camera_vertical_angle = pi/4

    zoom_factor = 0.0
    zoom_start_distance = 6.0
    zoom_last_distance = 6.0
    zoom_animation_speed = 0.1

    key_down_left_mouse = False

    mouse_drag_speed = 0.01
    mouse_scroll_speed = 0.5
    mouse_last_x = -1.0
    mouse_last_y = -1.0

    refresh_queued = False
    delta_time = None
    last_time = None
    n_leds = None

    hdr = [1.0, 0.0]
    hdr_goal = [1.0, 0.0]
    hdr_change_rate = 1.0
    hdr_id = None

    clear_color = Color('gray')
    debug = False
    fov = 45.0
    close = 0.01
    far = 1000
    fps = 60
    window_width = 800
    window_height = 600
    window_title = b'LED Visualizer'

    def __init__(self, model, led_colors):
        if len(model['led-strip']) != len(led_colors)//3:
            raise ValueError('LED color array does not fit current model')

        self.model = model
        self.led_colors = led_colors
        self.n_leds = len(model['led-strip'])
        self.last_time = time.time()

        def thread_func():
            self._init_glut()
            self._init_opengl()
            glutMainLoop()

        self.visualizer_thread = Thread(
            name='visualizer',
            target=thread_func)

        self.visualizer_thread.start()

    def _init_opengl(self):
        glClearColor(
            self.clear_color.get_red(),
            self.clear_color.get_green(),
            self.clear_color.get_blue(),
            1.0)
        glClearDepth(1.0)
        glDepthFunc(GL_LEQUAL)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_POLYGON_SMOOTH)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glEnable(GL_VERTEX_ARRAY)
        #glEnable(GL_BLEND)
        #glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        if not glUseProgram:
            raise EnvironmentError('Missing shader objects')

        # Open shader files
        vert_file = open('enclosure.vert')
        frag_file = open('enclosure.frag')

        # Compile
        self.program = compileProgram(
            compileShader(vert_file.read(), GL_VERTEX_SHADER),
            compileShader(frag_file.read(), GL_FRAGMENT_SHADER)
        )

        # Close files
        vert_file.close()
        frag_file.close()

        glUseProgram(self.program)

        # Fill LED buffers
        led_positions = self.model['led-strip']
        self.led_color_buffer = (GLfloat * (4*self.n_leds))(*ones(4*self.n_leds))
        self.led_position_buffer = (GLfloat * (4*self.n_leds))(*ones(4*self.n_leds))
        for i in range(self.n_leds):
            for j in range(3):
                self.led_color_buffer[i*4+j] = self.led_colors[i*3+j]/255.0
                self.led_position_buffer[i*4+j] = led_positions[i][j]

        # Fill enclosure buffer
        led_enclosure = self.model['led-enclosure']
        self.led_enclosure_buffer = (GLfloat * (3*4*len(led_enclosure)))(*ones(3*4*len(led_enclosure)))
        for i in range(len(led_enclosure)):
            for j in range(3):
                for k in range(3):
                    self.led_enclosure_buffer[i*4*3+j*4+k] = led_enclosure[i][j][k]

        # Generate vertex array and bind
        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)

        # Not the best way, but works for now
        self.attrib_led_color_id = glGetUniformLocation(self.program, 'led_colors')
        glUniform4fv(self.attrib_led_color_id, self.n_leds, self.led_color_buffer)

        self.attrib_led_position_id = glGetUniformLocation(self.program, 'led_positions')
        glUniform4fv(self.attrib_led_position_id, self.n_leds, self.led_position_buffer)

        self.hdr_id = glGetUniformLocation(self.program, 'hdr')

        """
        # Setup LED color buffer
        self.led_color_buffer_id = glGenBuffers(1)
        glBindBuffer(GL_UNIFORM_BUFFER, self.led_color_buffer_id)
        glBufferData(GL_UNIFORM_BUFFER, len(self.led_color_buffer) * sizeof(GLfloat),
                     self.led_color_buffer, GL_STREAM_DRAW)

        self.attrib_led_color_id = glGetUniformLocation(self.program, 'led_colors')
        glBindBufferRange(GL_UNIFORM_BUFFER, 0, self.led_color_buffer_id, 0, len(self.led_color_buffer_id))

        # Setup LED position buffer
        self.led_position_buffer_id = glGenBuffers(1)
        glBindBuffer(GL_UNIFORM_BUFFER, self.led_position_buffer_id)
        glBufferData(GL_UNIFORM_BUFFER, len(self.led_position_buffer) * sizeof(GLfloat),
                     self.led_position_buffer, GL_STATIC_DRAW)

        self.attrib_led_position_id = glGetUniformLocation(self.program, 'led_positions')
        glBindBufferBase(GL_UNIFORM_BUFFER, 1, self.led_position_buffer_id)
        glUniformBlockBinding(self.program, self.attrib_led_position_id, 1)
        """

        glBindBuffer(GL_UNIFORM_BUFFER, 0)

        # Setup enclosure vertex buffer
        self.led_enclosure_buffer_id = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.led_enclosure_buffer_id)
        glBufferData(GL_ARRAY_BUFFER, len(self.led_enclosure_buffer) * sizeof(GLfloat),
                     self.led_enclosure_buffer, GL_STATIC_DRAW)

        self.attrib_position_id = glGetAttribLocation(self.program, 'position')
        glVertexAttribPointer(self.attrib_position_id, 4, GL_FLOAT, GL_FALSE, 0, GLvoid)
        glEnableVertexAttribArray(self.attrib_position_id)

        glBindBuffer(GL_ARRAY_BUFFER, 0)

        glBindVertexArray(0)

        glUseProgram(0)

    def _init_glut(self):
        glutInit()
        glutInitDisplayMode(GLUT_DEPTH | GLUT_SINGLE | GLUT_RGB)
        glutInitWindowSize(self.window_width, self.window_height)
        glutCreateWindow(self.window_title)
        glutDisplayFunc(self._render)
        glutIdleFunc(self._render)
        glutMouseFunc(self._mouse_used)
        glutMouseWheelFunc(self._mouse_scroll_used)
        glutKeyboardFunc(self._keyboard_used)
        glutMotionFunc(self._motion)
        glutReshapeFunc(self._resize)

    def _update_hdr(self):
        self.hdr[0] += (self.hdr_goal[0] - self.hdr[0])*self.hdr_change_rate*self.delta_time
        self.hdr[1] += (self.hdr_goal[1] - self.hdr[1])*self.hdr_change_rate*self.delta_time

        glClearColor(
            self.clear_color.get_red()*self.hdr[0] - self.hdr[1],
            self.clear_color.get_green()*self.hdr[0] - self.hdr[1],
            self.clear_color.get_blue()*self.hdr[0] - self.hdr[1],
            1.0)
        glUniform2f(self.hdr_id, GLfloat(self.hdr[0]), GLfloat(self.hdr[1]))

    def _resize(self, width, height):
        if height == 0:
            height = 1

        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(self.fov, float(width)/float(height), self.close, self.far)
        glMatrixMode(GL_MODELVIEW)

    def _update_camera(self):
        zoom_distance_goal = pow(2.0, self.zoom_factor)*self.zoom_start_distance
        self.zoom_last_distance += (zoom_distance_goal - self.zoom_last_distance)*self.zoom_animation_speed

        gluLookAt(
            self.zoom_last_distance * cos(self.camera_horizontal_angle) * sin(self.camera_vertical_angle),
            self.zoom_last_distance * sin(self.camera_horizontal_angle) * sin(self.camera_vertical_angle),
            self.zoom_last_distance * cos(self.camera_vertical_angle),
            0, 0, 0,
            0, 0, 1)

    def _draw_model(self):
        glBindVertexArray(self.vao)
        glDrawArrays(GL_TRIANGLES, 0, len(self.led_enclosure_buffer))
        glBindVertexArray(0)

        if self.debug:
            pass

    def _render(self):
        now_time = time.time()
        self.delta_time = now_time - self.last_time
        self.last_time = now_time

        sync_time = 1./self.fps - self.delta_time
        if sync_time < 0:
            sync_time = 0
        time.sleep(sync_time)

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glLoadIdentity()

        glUseProgram(self.program)

        if self.refresh_queued:
            light_intensity = 0.0
            for i in range(self.n_leds):
                led_intensity = 0.0
                for j in range(3):
                    led = self.led_colors[i * 3 + j] / 255.0
                    led_intensity += led / 3.0
                    self.led_color_buffer[i * 4 + j] = led
                light_intensity += led_intensity
                self.led_color_buffer[i * 4 + 3] = 1.0
            light_intensity /= self.n_leds
            self.hdr_goal[1] = light_intensity*1.0
            glUniform4fv(self.attrib_led_color_id, self.n_leds, self.led_color_buffer)

            """
            glBindBuffer(GL_UNIFORM_BUFFER, self.led_buffer_color_index)
            glBufferSubData(GL_UNIFORM_BUFFER,
                            0,
                            len(self.led_buffer_colors)*sizeof(c_float),
                            self.led_buffer_colors)
            glBindBuffer(GL_UNIFORM_BUFFER, 0)
            """

            self.refresh_queued = False

        self._update_hdr()
        self._update_camera()
        self._draw_model()

        glutSwapBuffers()

        glUseProgram(0)

    def refresh(self):
        self.refresh_queued = True

    def running(self):
        return self.visualizer_thread.is_alive()

    def _keyboard_used(self, key, x, y):
        if key == 'esc':
            exit(0)
        elif key == 'd':
            self.debug = not self.debug

    def _mouse_used(self, button, state, x, y):
        if button == GLUT_LEFT_BUTTON:
            if state == GLUT_UP:
                self.key_down_left_mouse = False
                self.mouse_last_x = -1.0
                self.mouse_last_y = -1.0
            else:
                self.key_down_left_mouse = True

    def _mouse_scroll_used(self, wheel, direction, x, y):
        self.zoom_factor -= direction * self.mouse_scroll_speed

    def _motion(self, x, y):
        if self.key_down_left_mouse:
            if self.mouse_last_x == -1.0:
                self.mouse_last_x = x
                self.mouse_last_y = y
            self.camera_horizontal_angle -= (x - self.mouse_last_x)*self.mouse_drag_speed
            self.camera_horizontal_angle = self.camera_horizontal_angle % (2*pi)
            temp = self.camera_vertical_angle - (y - self.mouse_last_y)*self.mouse_drag_speed
            self.camera_vertical_angle = clip(temp, 0.001, pi - 0.001)
            self.mouse_last_x = x
            self.mouse_last_y = y


if __name__ == "__main__":
    # TODO: Make the model global for all the scripts and add error check
    model = 'cube'
    model_file = open('{}.json'.format(model))
    model_dict = json.loads(model_file.read())
    model_file.close()
    model_dict['name'] = model

    led_colors = [
        255, 0, 0,
        0, 255, 0,
        0, 0, 255]

    vis = LedVisualizer(model_dict, led_colors)
    vis.debug = True

    while vis.running():
        for i in range(len(led_colors)):
            led_colors[i] = randint(0, 255)
        vis.refresh()
        time.sleep(1)
